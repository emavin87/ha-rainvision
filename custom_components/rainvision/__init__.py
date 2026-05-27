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
from .const import DOMAIN, CONF_TOKEN, DEFAULT_MANUAL_DURATION
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT]

PROGRAMS_LIST = ["A", "B", "C", "D", "E", "F", "G", "H"]
ZONE_IDS = [1, 2, 4, 8]

# ── Service names ─────────────────────────────────────────────────────────────
SVC_MANUAL_START      = "manual_start"
SVC_MANUAL_STOP       = "manual_stop"
SVC_SET_ZONE_DURATION = "set_zone_duration"
SVC_SET_START_TIME    = "set_program_start_time"
SVC_SET_CYCLE         = "set_program_cycle"
SVC_SET_WEEKDAYS      = "set_program_weekdays"
SVC_SET_PROGRAMS      = "set_programs"

# ── Shared base schema for program-level services ─────────────────────────────
_PROG_BASE = {
    vol.Required("device_puid"): cv.string,
    vol.Required("program"): vol.In(PROGRAMS_LIST),
}

# ── Service validation schemas ────────────────────────────────────────────────

SCHEMA_MANUAL_START = vol.Schema({
    vol.Required("cloud_id"): vol.Coerce(int),
    vol.Required("device_id"): vol.Coerce(int),
    vol.Required("zone"): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
    vol.Optional("duration_minutes", default=DEFAULT_MANUAL_DURATION): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=120)
    ),
})

SCHEMA_MANUAL_STOP = vol.Schema({
    vol.Required("cloud_id"): vol.Coerce(int),
    vol.Required("device_id"): vol.Coerce(int),
})

SCHEMA_SET_ZONE_DURATION = vol.Schema({
    **_PROG_BASE,
    vol.Required("zone_id"): vol.In(ZONE_IDS),
    vol.Required("duration_seconds"): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=7200)
    ),
})

SCHEMA_SET_START_TIME = vol.Schema({
    **_PROG_BASE,
    vol.Required("time_index"): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=5)
    ),
    vol.Required("time"): cv.string,    # "HH:MM"
    vol.Required("active"): cv.boolean,
})

SCHEMA_SET_CYCLE = vol.Schema({
    **_PROG_BASE,
    vol.Required("cycle_hours"): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=168)
    ),
})

SCHEMA_SET_WEEKDAYS = vol.Schema({
    **_PROG_BASE,
    vol.Required("weekdays"): [vol.All(vol.Coerce(int), vol.Range(min=1, max=7))],
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
        _LOGGER.error("Rain Vision: cannot authenticate: %s", err)
        return False

    coordinator = RainVisionCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ── Helper: run API call, refresh coordinator on success ──────────────────

    async def _call(coro, label: str) -> None:
        try:
            success = await coro
            if success:
                await coordinator.async_request_refresh()
                _LOGGER.info("Rain Vision: %s succeeded", label)
            else:
                _LOGGER.error("Rain Vision: %s failed (negative response)", label)
        except (RainVisionApiError, RainVisionAuthError) as err:
            _LOGGER.error("Rain Vision: error in %s: %s", label, err)

    # ── Service handlers ──────────────────────────────────────────────────────

    async def handle_manual_start(call: ServiceCall) -> None:
        """Start manual irrigation on a specific zone.

        Example:
          service: rainvision.manual_start
          data:
            cloud_id: 1099
            device_id: 5644
            zone: 1
            duration_minutes: 10
        """
        await _call(
            api.manual_start_zone(
                call.data["cloud_id"],
                call.data["device_id"],
                call.data["zone"],
                call.data["duration_minutes"],
            ),
            SVC_MANUAL_START,
        )

    async def handle_manual_stop(call: ServiceCall) -> None:
        """Stop all manual irrigation on a device.

        Example:
          service: rainvision.manual_stop
          data:
            cloud_id: 1099
            device_id: 5644
        """
        await _call(
            api.manual_stop(
                call.data["cloud_id"],
                call.data["device_id"],
            ),
            SVC_MANUAL_STOP,
        )

    async def handle_set_zone_duration(call: ServiceCall) -> None:
        """Update irrigation duration for one zone in a program.

        Example:
          service: rainvision.set_zone_duration
          data:
            device_puid: "1000005059"
            program: "A"
            zone_id: 1
            duration_seconds: 900
        """
        await _call(
            api.set_zone_duration_in_program(
                call.data["device_puid"],
                call.data["program"],
                call.data["zone_id"],
                call.data["duration_seconds"],
            ),
            SVC_SET_ZONE_DURATION,
        )

    async def handle_set_start_time(call: ServiceCall) -> None:
        """Update a start time slot for a program.

        Each program has up to 6 time slots (time_index 0-5).

        Example:
          service: rainvision.set_program_start_time
          data:
            device_puid: "1000005059"
            program: "A"
            time_index: 0
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
            SVC_SET_START_TIME,
        )

    async def handle_set_cycle(call: ServiceCall) -> None:
        """Update how often a program repeats (cycle frequency in hours).

        Example:
          service: rainvision.set_program_cycle
          data:
            device_puid: "1000005059"
            program: "A"
            cycle_hours: 48
        """
        await _call(
            api.set_program_cycle(
                call.data["device_puid"],
                call.data["program"],
                call.data["cycle_hours"],
            ),
            SVC_SET_CYCLE,
        )

    async def handle_set_weekdays(call: ServiceCall) -> None:
        """Update the weekdays on which a program runs.

        Day indexes: 1=Sun, 2=Mon, 3=Tue, 4=Wed, 5=Thu, 6=Fri, 7=Sat

        Example:
          service: rainvision.set_program_weekdays
          data:
            device_puid: "1000005059"
            program: "A"
            weekdays: [2, 4, 6]
        """
        await _call(
            api.set_program_weekdays(
                call.data["device_puid"],
                call.data["program"],
                call.data["weekdays"],
            ),
            SVC_SET_WEEKDAYS,
        )

    async def handle_set_programs(call: ServiceCall) -> None:
        """Send a full programs payload to the device.

        Example:
          service: rainvision.set_programs
          data:
            device_puid: "1000005059"
            programs: [...]
        """
        await _call(
            api.set_device_programs(
                call.data["device_puid"],
                call.data["programs"],
            ),
            SVC_SET_PROGRAMS,
        )

    # ── Register all services ─────────────────────────────────────────────────

    for name, handler, schema in [
        (SVC_MANUAL_START,      handle_manual_start,      SCHEMA_MANUAL_START),
        (SVC_MANUAL_STOP,       handle_manual_stop,       SCHEMA_MANUAL_STOP),
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
