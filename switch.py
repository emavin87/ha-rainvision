"""Switch platform for the Rainvision integration.

Creates one switch per irrigation program (A–D) that reflects whether the
program is currently listed in the device's active_programs field.

Note on write support:
    The Rainvision cloud API does not expose a documented endpoint for
    enabling or disabling individual programs remotely. The turn_on /
    turn_off handlers therefore log a warning and take no action.
    If Rainvision publishes such an endpoint in the future, implement it
    in api.py and call it from async_turn_on / async_turn_off below.
"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COORDINATOR_DEVICE
from .coordinator import RainvisionCoordinator

_LOGGER = logging.getLogger(__name__)

# Programs exposed by the PURE VISION-EV controller
PROGRAMS = ["A", "B", "C", "D"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one switch entity per irrigation program."""
    coordinator: RainvisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        RainvisionProgramSwitch(coordinator, prog, entry.entry_id)
        for prog in PROGRAMS
    )


class RainvisionProgramSwitch(
    CoordinatorEntity[RainvisionCoordinator], SwitchEntity
):
    """Read-only switch that reflects the active state of an irrigation program.

    is_on is True when the program letter appears in the device's
    active_programs string returned by nuvola/device.
    """

    def __init__(
        self,
        coordinator: RainvisionCoordinator,
        program: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._program = program
        self._attr_unique_id = f"{entry_id}_program_{program.lower()}"
        self._attr_name = f"Program {program}"
        self._attr_icon = "mdi:sprinkler-variant"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_puid)},
            name="Rainvision",
            manufacturer="Rainvision",
            model="PURE VISION-EV",
        )

    @property
    def is_on(self) -> bool:
        """Return True if this program is in the active_programs list.

        active_programs is returned as '[A,B,C,D]' by the API; strip the
        brackets and split on commas before checking membership.
        """
        try:
            raw = self.coordinator.data[COORDINATOR_DEVICE]["device"]["active_programs"]
            active = raw.strip("[]").split(",")
            return self._program in active
        except (KeyError, TypeError, AttributeError):
            return False

    async def async_turn_on(self, **kwargs) -> None:
        """Not supported — no public API endpoint to enable programs remotely.

        Use the Rainvision app to modify program schedules, or extend this
        method once a suitable endpoint becomes available.
        """
        _LOGGER.warning(
            "Program %s cannot be enabled via the cloud API "
            "(no documented endpoint). Use the Rainvision app instead.",
            self._program,
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Not supported — see async_turn_on for details."""
        _LOGGER.warning(
            "Program %s cannot be disabled via the cloud API "
            "(no documented endpoint). Use the Rainvision app instead.",
            self._program,
        )
