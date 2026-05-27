"""Config flow for Rain Vision integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RainVisionApi, RainVisionAuthError, RainVisionApiError
from .const import DOMAIN, CONF_TOKEN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class RainVisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Rain Vision."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            api = RainVisionApi(session)

            try:
                token = await api.authenticate(email, password)
            except RainVisionAuthError:
                errors["base"] = "invalid_auth"
            except RainVisionApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Rain Vision login")
                errors["base"] = "unknown"
            else:
                # Avoid duplicate entries for the same account
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Rain Vision ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_TOKEN: token,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
