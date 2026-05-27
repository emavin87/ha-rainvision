"""Rainvision integration for Home Assistant.

Sets up a single config entry per Nuvola hub. Each entry creates:
  - One RainvisionApiClient (authenticated HTTP client)
  - One RainvisionCoordinator (shared data poller)
  - Sensor, binary_sensor, and switch platform entities
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RainvisionApiClient, RainvisionAuthError, RainvisionConnectionError
from .coordinator import RainvisionCoordinator
from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_CLOUD_PUID,
    CONF_DEVICE_PUID,
)

_LOGGER = logging.getLogger(__name__)

# Platforms registered by this integration
PLATFORMS = ["sensor", "binary_sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rainvision from a config entry.

    On every HA startup the stored Bearer token is validated via POST
    /check-token. If the token has expired a fresh one is obtained via POST
    /token and written back to the config entry so subsequent restarts reuse
    the new token automatically.

    After a valid token is confirmed the coordinator performs its first data
    fetch before any platform entities are registered.
    """
    session = async_get_clientsession(hass)
    client = RainvisionApiClient(session, token=entry.data[CONF_TOKEN])

    # Validate the stored token; re-authenticate if it has expired
    token_valid = await client.check_token()
    if not token_valid:
        _LOGGER.info("Stored token expired — re-authenticating with Rainvision")
        try:
            new_token = await client.authenticate(
                entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
            )
        except (RainvisionAuthError, RainvisionConnectionError) as err:
            _LOGGER.error("Re-authentication failed: %s", err)
            # Persist the failure so HA shows a re-auth notification to the user
            hass.config_entries.async_start_reauth(entry)
            return False

        # Persist the new token so the next startup skips re-authentication
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKEN: new_token}
        )
        _LOGGER.debug("Token refreshed and saved to config entry")

    coordinator = RainvisionCoordinator(
        hass,
        client,
        cloud_puid=entry.data[CONF_CLOUD_PUID],
        device_puid=entry.data[CONF_DEVICE_PUID],
    )

    # Perform the first refresh synchronously so entities have data immediately
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator so platform modules can retrieve it by entry_id
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Rainvision config entry and clean up stored data."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
