"""Config flow for the Rainvision integration.

Presents a single form that collects credentials and device PUIDs,
authenticates against the Rainvision cloud, and stores the resulting
Bearer token in the config entry data.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RainvisionApiClient, RainvisionAuthError, RainvisionConnectionError
from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_CLOUD_PUID,
    CONF_DEVICE_PUID,
    CONF_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

# Schema for the initial user setup step
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        # Suggested values match the PUIDs found in the HAR capture
        vol.Required(CONF_CLOUD_PUID, description={"suggested_value": "2000001121"}): str,
        vol.Required(CONF_DEVICE_PUID, description={"suggested_value": "1000005059"}): str,
    }
)


class RainvisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Rainvision integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step shown to the user.

        Validates credentials by attempting a real login; stores the token
        on success so the coordinator can use it without re-authenticating.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = RainvisionApiClient(session)

            try:
                token = await client.authenticate(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except RainvisionAuthError:
                errors["base"] = "invalid_auth"
            except RainvisionConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                # Use cloud_puid as the unique identifier to prevent duplicates
                await self.async_set_unique_id(user_input[CONF_CLOUD_PUID])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Rainvision ({user_input[CONF_CLOUD_PUID]})",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_CLOUD_PUID: user_input[CONF_CLOUD_PUID],
                        CONF_DEVICE_PUID: user_input[CONF_DEVICE_PUID],
                        CONF_TOKEN: token,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle re-authentication when the stored token has expired."""
        return await self.async_step_user(user_input)
