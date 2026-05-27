"""Rain Vision integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RainVisionApi, RainVisionAuthError, RainVisionApiError
from .const import DOMAIN, CONF_TOKEN
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rain Vision from a config entry."""
    session = async_get_clientsession(hass)
    api = RainVisionApi(session)

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    stored_token = entry.data.get(CONF_TOKEN)

    # Set stored token then verify it, re-authenticate if expired
    if stored_token:
        api.token = stored_token

    try:
        token = await api.ensure_authenticated(email, password)
        # Persist refreshed token if it changed
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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Rain Vision config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
