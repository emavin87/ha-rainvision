"""Binary sensor platform for the Rainvision integration.

Exposes connectivity status and per-program weather-gate flags.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COORDINATOR_DEVICE, COORDINATOR_PROGRAMS
from .coordinator import RainvisionCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RainvisionBinarySensorDescription(BinarySensorEntityDescription):
    """Extends BinarySensorEntityDescription with a value extractor callback.

    value_fn: Receives coordinator.data and returns bool | None.
    """
    value_fn: Any = None


# ---------------------------------------------------------------------------
# Value extractor functions
# ---------------------------------------------------------------------------

def _is_connected(data: dict) -> bool:
    """Return True when the last nuvola/device call succeeded.

    Uses the top-level 'success' flag in the API response.
    """
    try:
        return bool(data[COORDINATOR_DEVICE].get("success"))
    except (KeyError, TypeError):
        return False


def _prog_a_should_run(data: dict) -> bool | None:
    """Return whether the weather algorithm allows program A to run.

    Reads should_run from meteo_pause_json for program 'A'.
    Returns None if the data is unavailable.
    """
    try:
        raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        meteo = json.loads(raw)
        prog_a = next((p for p in meteo if p["name"] == "A"), None)
        return prog_a["should_run"] if prog_a else None
    except Exception:
        return None


def _prog_b_should_run(data: dict) -> bool | None:
    """Return whether the weather algorithm allows program B to run.

    Reads should_run from meteo_pause_json for program 'B'.
    Returns None if the data is unavailable.
    """
    try:
        raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        meteo = json.loads(raw)
        prog_b = next((p for p in meteo if p["name"] == "B"), None)
        return prog_b["should_run"] if prog_b else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Binary sensor descriptors
# ---------------------------------------------------------------------------

BINARY_SENSOR_DESCRIPTIONS: tuple[RainvisionBinarySensorDescription, ...] = (
    RainvisionBinarySensorDescription(
        key="connected",
        name="Cloud connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:cloud-check",
        value_fn=_is_connected,
    ),
    RainvisionBinarySensorDescription(
        key="prog_a_should_run",
        name="Program A — weather OK",
        icon="mdi:weather-sunny",
        value_fn=_prog_a_should_run,
    ),
    RainvisionBinarySensorDescription(
        key="prog_b_should_run",
        name="Program B — weather OK",
        icon="mdi:weather-sunny",
        value_fn=_prog_b_should_run,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rainvision binary sensor entities from a config entry."""
    coordinator: RainvisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        RainvisionBinarySensor(coordinator, description, entry.entry_id)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class RainvisionBinarySensor(
    CoordinatorEntity[RainvisionCoordinator], BinarySensorEntity
):
    """Generic Rainvision binary sensor driven by a descriptor."""

    entity_description: RainvisionBinarySensorDescription

    def __init__(
        self,
        coordinator: RainvisionCoordinator,
        description: RainvisionBinarySensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_puid)},
            name="Rainvision",
            manufacturer="Rainvision",
            model="PURE VISION-EV",
        )

    @property
    def is_on(self) -> bool | None:
        """Call the descriptor's value_fn with the latest coordinator data."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None
