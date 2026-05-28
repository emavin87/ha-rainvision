"""
Rain Vision Config Flow
========================
Handles the guided setup UI shown when the user adds the Rain Vision
integration via Settings → Devices & Services → Add Integration.

The flow:
  1. Show a form asking for email and password.
  2. Attempt login via RainVisionApi.authenticate().
  3. On success, create the config entry storing email, password and token.
  4. On failure, show an inline error and let the user try again.

A unique_id based on the account email prevents duplicate entries for
the same Rain Vision account.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RainVisionApi, RainVisionAuthError, RainVisionApiError
from .const import DOMAIN, CONF_TOKEN

_LOGGER = logging.getLogger(__name__)

# Schema for the user-facing login form
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL):    str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class RainVisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the Rain Vision integration.

    Presents a single-step form that collects email and password,
    validates them against the Rain Vision API, and creates the
    config entry on success.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial (and only) setup step.

        Args:
            user_input: Dict with 'email' and 'password' keys when the
                        user submits the form, or None on first display.

        Returns:
            A FlowResult showing the form or creating the config entry.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            email    = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            api     = RainVisionApi(session)

            try:
                token = await api.authenticate(email, password)
            except RainVisionAuthError:
                errors["base"] = "invalid_auth"
            except RainVisionApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Rain Vision login")
                errors["base"] = "unknown"
            else:
                # Prevent duplicate entries for the same account
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Rain Vision ({email})",
                    data={
                        CONF_EMAIL:    email,
                        CONF_PASSWORD: password,
                        CONF_TOKEN:    token,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
