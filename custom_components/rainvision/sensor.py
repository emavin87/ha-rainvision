"""Sensor platform for the Rainvision integration.

Creates one sensor entity per data point exposed by the API, plus one
dynamic zone sensor per irrigation zone returned by GetZoneNames.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COORDINATOR_DEVICE, COORDINATOR_STAT, COORDINATOR_PROGRAMS
from .coordinator import RainvisionCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RainvisionSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with extractor callbacks.

    value_fn: Receives coordinator.data and returns the sensor's native value.
    attr_fn:  Receives coordinator.data and returns extra_state_attributes dict.
    """
    value_fn: Any = None
    attr_fn: Any = None


# ---------------------------------------------------------------------------
# Value extractor functions
# Each function receives the full coordinator.data dict and returns the value
# for a specific sensor, or None when the path is unavailable.
# ---------------------------------------------------------------------------

def _battery_device(data: dict) -> int | None:
    """Extract battery level from the nuvola/device response."""
    try:
        return data[COORDINATOR_DEVICE]["data"]["status"]["battery"]
    except (KeyError, TypeError):
        return None


def _battery_cloud(data: dict) -> int | None:
    """Extract battery level of the Nuvola hub from the nuvola/stat response."""
    try:
        return data[COORDINATOR_STAT]["cloud"]["battery"]
    except (KeyError, TypeError):
        return None


def _active_programs(data: dict) -> str | None:
    """Return the active programs as a space-separated string (e.g. 'A B C D').

    The API returns the raw value as '[A,B,C,D]'.
    """
    try:
        raw = data[COORDINATOR_DEVICE]["device"]["active_programs"]
        return raw.strip("[]").replace(",", " ") if raw else None
    except (KeyError, TypeError):
        return None


def _firmware(data: dict) -> int | None:
    """Extract the firmware ID of the irrigation device."""
    try:
        return data[COORDINATOR_DEVICE]["device"]["firmware_id"]
    except (KeyError, TypeError):
        return None


def _meteo_temp(data: dict) -> float | None:
    """Extract the forecast temperature used by the weather-pause algorithm (°C).

    Source: device.meteo_pause_json[0].temp from GetProgramNames.
    """
    try:
        meteo_raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        meteo = json.loads(meteo_raw)
        return float(meteo[0]["temp"])
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _meteo_rain(data: dict) -> float | None:
    """Extract probability of precipitation as a percentage (0–100).

    The API returns 'pop' as a 0–1 float; multiply by 100 for display.
    Source: device.meteo_pause_json[0].pop from GetProgramNames.
    """
    try:
        meteo_raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        meteo = json.loads(meteo_raw)
        return round(float(meteo[0]["pop"]) * 100, 1)
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _meteo_wind(data: dict) -> float | None:
    """Extract wind speed (m/s) used by the weather-pause algorithm.

    Source: device.meteo_pause_json[0].wind from GetProgramNames.
    """
    try:
        meteo_raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        meteo = json.loads(meteo_raw)
        return float(meteo[0]["wind"])
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _irrigation_variable(data: dict) -> float | None:
    """Extract the computed irrigation adjustment variable as a percentage.

    Rainvision calculates this coefficient from weather data to modulate
    program durations. Range is 0–100 (API value 0–1 multiplied by 100).
    Source: device.meteo_pause_json[0].irrigation_variable from GetProgramNames.
    """
    try:
        meteo_raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        meteo = json.loads(meteo_raw)
        return round(float(meteo[0]["irrigation_variable"]) * 100, 1)
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _meteo_attrs(data: dict) -> dict:
    """Return the full meteo_pause_json list as extra attributes.

    Useful for automations that need per-program weather variables.
    """
    try:
        meteo_raw = data[COORDINATOR_PROGRAMS]["device"]["meteo_pause_json"]
        return json.loads(meteo_raw)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Static sensor descriptors
# ---------------------------------------------------------------------------

SENSOR_DESCRIPTIONS: tuple[RainvisionSensorDescription, ...] = (
    RainvisionSensorDescription(
        key="battery_device",
        name="Irrigation device battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        value_fn=_battery_device,
    ),
    RainvisionSensorDescription(
        key="battery_cloud",
        name="Hub battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        value_fn=_battery_cloud,
    ),
    RainvisionSensorDescription(
        key="active_programs",
        name="Active programs",
        icon="mdi:calendar-clock",
        value_fn=_active_programs,
    ),
    RainvisionSensorDescription(
        key="firmware",
        name="Firmware version",
        icon="mdi:chip",
        value_fn=_firmware,
    ),
    RainvisionSensorDescription(
        key="meteo_temperature",
        name="Weather temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_meteo_temp,
    ),
    RainvisionSensorDescription(
        key="meteo_rain_probability",
        name="Rain probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=_meteo_rain,
    ),
    RainvisionSensorDescription(
        key="meteo_wind",
        name="Wind speed",
        native_unit_of_measurement="m/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=_meteo_wind,
    ),
    RainvisionSensorDescription(
        key="irrigation_variable",
        name="Irrigation adjustment",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=_irrigation_variable,
        # Expose all per-program weather data as attributes
        attr_fn=_meteo_attrs,
    ),
)

# Separate from SENSOR_DESCRIPTIONS because this sensor reads coordinator
# metadata directly instead of coordinator.data.
LAST_UPDATE_DESCRIPTION = RainvisionSensorDescription(
    key="last_update",
    name="Last data update",
    device_class=SensorDeviceClass.TIMESTAMP,
    icon="mdi:clock-check-outline",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rainvision sensor entities from a config entry."""
    coordinator: RainvisionCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Add all statically defined sensors
    async_add_entities(
        RainvisionSensor(coordinator, description, entry.entry_id)
        for description in SENSOR_DESCRIPTIONS
    )

    # Add the last-update timestamp sensor (reads coordinator metadata, not data)
    async_add_entities([RainvisionLastUpdateSensor(coordinator, entry.entry_id)])

    # Add one sensor per irrigation zone using names from GetZoneNames
    try:
        zones_data = coordinator.data[COORDINATOR_PROGRAMS]["device"].get("fullzonenames", [])
        async_add_entities(
            RainvisionZoneSensor(coordinator, zone, entry.entry_id)
            for zone in zones_data
        )
    except (KeyError, TypeError):
        _LOGGER.warning("Could not create zone sensors — zone data unavailable")


# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------

class RainvisionSensor(CoordinatorEntity[RainvisionCoordinator], SensorEntity):
    """Generic Rainvision sensor driven by a RainvisionSensorDescription."""

    entity_description: RainvisionSensorDescription

    def __init__(
        self,
        coordinator: RainvisionCoordinator,
        description: RainvisionSensorDescription,
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
    def native_value(self) -> Any:
        """Call the descriptor's value_fn with the latest coordinator data."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        """Call the descriptor's attr_fn if present."""
        if self.entity_description.attr_fn:
            return self.entity_description.attr_fn(self.coordinator.data)
        return None


class RainvisionZoneSensor(CoordinatorEntity[RainvisionCoordinator], SensorEntity):
    """Sensor representing a single irrigation zone.

    Created dynamically at setup time based on the zones returned by
    GetZoneNames → device.fullzonenames.
    The entity name uses the user-defined custom_name when available,
    falling back to the API's default_name.
    """

    def __init__(
        self,
        coordinator: RainvisionCoordinator,
        zone_data: dict,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._zone = zone_data
        zone_id = zone_data.get("zone_progressive", zone_data.get("id", "?"))
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}"
        self._attr_name = (
            zone_data.get("custom_name") or zone_data.get("default_name", f"Zone {zone_id}")
        )
        self._attr_icon = "mdi:sprinkler"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_puid)},
            name="Rainvision",
            manufacturer="Rainvision",
            model="PURE VISION-EV",
        )

    @property
    def native_value(self) -> str:
        """Return the zone's display name as the state value."""
        return self._zone.get("custom_name") or self._zone.get("default_name", "—")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose zone metadata for use in automations and templates."""
        return {
            "zone_progressive": self._zone.get("zone_progressive"),
            "default_name": self._zone.get("default_name"),
            "custom_name": self._zone.get("custom_name"),
        }


class RainvisionLastUpdateSensor(CoordinatorEntity[RainvisionCoordinator], SensorEntity):
    """Timestamp sensor that exposes when the coordinator last fetched data.

    Uses coordinator.last_update_success_time, which HA's DataUpdateCoordinator
    sets automatically after every successful _async_update_data() call.
    The value is a timezone-aware datetime; HA displays it using the user's
    configured timezone. device_class=TIMESTAMP enables the history graph and
    "time ago" rendering in the frontend.
    """

    def __init__(self, coordinator: RainvisionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self.entity_description = LAST_UPDATE_DESCRIPTION
        self._attr_unique_id = f"{entry_id}_last_update"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_puid)},
            name="Rainvision",
            manufacturer="Rainvision",
            model="PURE VISION-EV",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last successful coordinator update.

        last_update_success_time is a UTC-aware datetime set by the base
        DataUpdateCoordinator class. Returns None if no successful update has
        occurred yet (e.g. during the very first startup before data arrives).
        """
        return self.coordinator.last_update_success_time
