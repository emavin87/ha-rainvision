"""
Rain Vision Config Flow
========================
Handles the guided setup UI shown when the user adds the Rain Vision
integration via Settings → Devices & Services → Add Integration.

The flow:
  1. Show a form asking for email, password and polling interval.
  2. Attempt login via RainVisionApi.authenticate().
  3. On success, create the config entry storing email, password, token
     and scan_interval.
  4. On failure, show an inline error and let the user try again.

A OptionsFlow is also provided so the user can change the polling
interval later without re-entering credentials.

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
from .const import (
    DOMAIN,
    CONF_TOKEN,
    CONF_SCAN_INTERVAL,
    UPDATE_INTERVAL,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# Schema for the user-facing login form (step 1)
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL):    str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=UPDATE_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        ),
    }
)

# Schema for the options flow (change polling interval without re-login)
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SCAN_INTERVAL, default=UPDATE_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
        ),
    }
)


class RainVisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the Rain Vision integration.

    Presents a single-step form that collects email, password and the
    desired polling interval (in seconds), validates the credentials
    against the Rain Vision API, and creates the config entry on success.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial setup step.

        Args:
            user_input: Dict with 'email', 'password' and 'scan_interval'
                        when the user submits the form, or None on first display.

        Returns:
            A FlowResult showing the form or creating the config entry.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            email         = user_input[CONF_EMAIL]
            password      = user_input[CONF_PASSWORD]
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, UPDATE_INTERVAL)

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
                        CONF_EMAIL:         email,
                        CONF_PASSWORD:      password,
                        CONF_TOKEN:         token,
                        CONF_SCAN_INTERVAL: scan_interval,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler for this integration."""
        return RainVisionOptionsFlow(config_entry)


class RainVisionOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Rain Vision.

    Allows the user to change the polling interval from the integration
    settings page without re-entering credentials.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the options form.

        Pre-fills the current scan_interval value so the user sees
        what is currently configured.
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.data.get(CONF_SCAN_INTERVAL, UPDATE_INTERVAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
