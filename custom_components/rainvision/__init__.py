"""Rain Vision integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RainVisionApi, RainVisionAuthError, RainVisionApiError
from .const import DOMAIN, CONF_TOKEN
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

PROGRAMS_LIST = ["A", "B", "C", "D", "E", "F", "G", "H"]
ZONE_IDS = [1, 2, 4, 8]

# Service schemas
SVC_SET_ZONE_DURATION = "set_zone_duration"
SVC_SET_START_TIME    = "set_program_start_time"
SVC_SET_CYCLE         = "set_program_cycle"
SVC_SET_WEEKDAYS      = "set_program_weekdays"
SVC_SET_PROGRAMS      = "set_programs"

_BASE = {
    vol.Required("device_puid"): cv.string,
    vol.Required("program"): vol.In(PROGRAMS_LIST),
}

SCHEMA_SET_ZONE_DURATION = vol.Schema({
    **_BASE,
    vol.Required("zone_id"): vol.In(ZONE_IDS),
    vol.Required("duration_seconds"): vol.All(int, vol.Range(min=0, max=7200)),
})

SCHEMA_SET_START_TIME = vol.Schema({
    **_BASE,
    vol.Required("time_index"): vol.All(int, vol.Range(min=0, max=5)),
    vol.Required("time"): cv.string,   # "HH:MM"
    vol.Required("active"): cv.boolean,
})

SCHEMA_SET_CYCLE = vol.Schema({
    **_BASE,
    vol.Required("cycle_hours"): vol.All(int, vol.Range(min=1, max=168)),
})

SCHEMA_SET_WEEKDAYS = vol.Schema({
    **_BASE,
    vol.Required("weekdays"): [vol.All(int, vol.Range(min=1, max=7))],
})

SCHEMA_SET_PROGRAMS = vol.Schema({
    vol.Required("device_puid"): cv.string,
    vol.Required("programs"): list,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rain Vision from a config entry."""
    session = async_get_clientsession(hass)
    api = RainVisionApi(session)

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    stored_token = entry.data.get(CONF_TOKEN)

    if stored_token:
        api.token = stored_token

    try:
        token = await api.ensure_authenticated(email, password)
        if token != stored_token:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_TOKEN: token}
            )
    except (RainVisionAuthError, RainVisionApiError) as err:
        _LOGGER.error("Rain Vision: impossibile autenticarsi: %s", err)
        return False

    coordinator = RainVisionCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _call(coro, label: str) -> None:
        """Execute an API coroutine, refresh coordinator on success."""
        try:
            success = await coro
            if success:
                await coordinator.async_request_refresh()
                _LOGGER.info("Rain Vision: %s aggiornato", label)
            else:
                _LOGGER.error("Rain Vision: %s fallito (risposta negativa)", label)
        except (RainVisionApiError, RainVisionAuthError) as err:
            _LOGGER.error("Rain Vision: errore %s: %s", label, err)

    # ── service handlers ─────────────────────────────────────────────────────

    async def handle_set_zone_duration(call: ServiceCall) -> None:
        """rainvision.set_zone_duration — modifica durata di una zona.

        Esempio:
          service: rainvision.set_zone_duration
          data:
            device_puid: "1000005059"
            program: "A"
            zone_id: 1          # 1=Zona1, 2=Zona2, 4=Zona3, 8=Zona4
            duration_seconds: 900
        """
        await _call(
            api.set_zone_duration_in_program(
                call.data["device_puid"],
                call.data["program"],
                call.data["zone_id"],
                call.data["duration_seconds"],
            ),
            "set_zone_duration",
        )

    async def handle_set_start_time(call: ServiceCall) -> None:
        """rainvision.set_program_start_time — modifica orario di partenza.

        Ogni programma ha fino a 6 slot orari (time_index 0-5).
        Esempio:
          service: rainvision.set_program_start_time
          data:
            device_puid: "1000005059"
            program: "A"
            time_index: 0       # primo slot
            time: "06:30"
            active: true
        """
        await _call(
            api.set_program_start_time(
                call.data["device_puid"],
                call.data["program"],
                call.data["time_index"],
                call.data["time"],
                call.data["active"],
            ),
            "set_program_start_time",
        )

    async def handle_set_cycle(call: ServiceCall) -> None:
        """rainvision.set_program_cycle — modifica ogni quante ore parte il programma.

        Esempio:
          service: rainvision.set_program_cycle
          data:
            device_puid: "1000005059"
            program: "A"
            cycle_hours: 48     # ogni 2 giorni
        """
        await _call(
            api.set_program_cycle(
                call.data["device_puid"],
                call.data["program"],
                call.data["cycle_hours"],
            ),
            "set_program_cycle",
        )

    async def handle_set_weekdays(call: ServiceCall) -> None:
        """rainvision.set_program_weekdays — modifica i giorni della settimana.

        Esempio:
          service: rainvision.set_program_weekdays
          data:
            device_puid: "1000005059"
            program: "A"
            weekdays: [2, 4, 6]  # Lunedì, Mercoledì, Venerdì
        """
        await _call(
            api.set_program_weekdays(
                call.data["device_puid"],
                call.data["program"],
                call.data["weekdays"],
            ),
            "set_program_weekdays",
        )

    async def handle_set_programs(call: ServiceCall) -> None:
        """rainvision.set_programs — invia payload completo di programmi."""
        await _call(
            api.set_device_programs(
                call.data["device_puid"],
                call.data["programs"],
            ),
            "set_programs",
        )

    # ── register ─────────────────────────────────────────────────────────────

    for name, handler, schema in [
        (SVC_SET_ZONE_DURATION, handle_set_zone_duration, SCHEMA_SET_ZONE_DURATION),
        (SVC_SET_START_TIME,    handle_set_start_time,    SCHEMA_SET_START_TIME),
        (SVC_SET_CYCLE,         handle_set_cycle,         SCHEMA_SET_CYCLE),
        (SVC_SET_WEEKDAYS,      handle_set_weekdays,      SCHEMA_SET_WEEKDAYS),
        (SVC_SET_PROGRAMS,      handle_set_programs,      SCHEMA_SET_PROGRAMS),
    ]:
        hass.services.async_register(DOMAIN, name, handler, schema=schema)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Rain Vision config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
