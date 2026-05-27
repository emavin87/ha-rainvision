"""Sensor entities for Rain Vision."""
from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_CLOUD, MODEL_DEVICE
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rain Vision sensors."""
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for cloud_id, cloud in coordinator.clouds.items():
        # Nuvola battery sensor
        entities.append(RainVisionCloudBatterySensor(coordinator, cloud_id))

        for device in cloud.get("devices", []):
            device_id = device["id"]
            # Device battery sensor
            entities.append(RainVisionDeviceBatterySensor(coordinator, cloud_id, device_id))
            # Active programs sensor
            entities.append(RainVisionActiveProgramsSensor(coordinator, cloud_id, device_id))
            # Meteo pause sensor
            entities.append(RainVisionMeteoPauseSensor(coordinator, cloud_id, device_id))

    async_add_entities(entities)


def _cloud_device_info(cloud: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"cloud_{cloud['id']}")},
        name=cloud.get("name", f"Nuvola {cloud['id']}"),
        manufacturer=MANUFACTURER,
        model=MODEL_CLOUD,
        sw_version=cloud.get("firmwarecloud", {}).get("name"),
    )


def _device_device_info(device: dict, cloud: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"device_{device['id']}")},
        name=device.get("name", f"Device {device['id']}"),
        manufacturer=MANUFACTURER,
        model=device.get("devicetype", {}).get("name", MODEL_DEVICE),
        sw_version=device.get("firmware", {}).get("name"),
        via_device=(DOMAIN, f"cloud_{cloud['id']}"),
    )


class RainVisionCloudBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery sensor for Nuvola cloud hub."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._attr_unique_id = f"cloud_{cloud_id}_battery"

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Batteria"

    @property
    def native_value(self) -> int | None:
        return self._cloud.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_device_info(self._cloud)


class RainVisionDeviceBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery sensor for a Pure Vision device."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._attr_unique_id = f"device_{device_id}_battery"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Batteria"

    @property
    def native_value(self) -> int | None:
        return self._device.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)


class RainVisionActiveProgramsSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing which programs are currently active."""

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._attr_unique_id = f"device_{device_id}_active_programs"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Programmi Attivi"

    @property
    def native_value(self) -> str | None:
        raw = self._device.get("active_programs", "")
        # Format is "[A,B,C,D]" — clean it up
        return raw.strip("[]").replace(",", ", ") if raw else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose each program name and its active state."""
        device = self._device
        active_raw = device.get("active_programs", "")
        active_letters = set(active_raw.strip("[]").split(","))

        programs: dict[str, str] = {}
        for prog in device.get("fullprogramnames", []):
            letter = prog.get("program_progressive", "")
            custom = prog.get("custom_name") or prog.get("default_name", letter)
            programs[f"program_{letter}"] = custom
            programs[f"program_{letter}_active"] = letter in active_letters

        return programs

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)


class RainVisionMeteoPauseSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing meteo pause status for programs."""

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._attr_unique_id = f"device_{device_id}_meteo_pause"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Pausa Meteo"

    @property
    def native_value(self) -> str:
        """Return whether any program is paused due to meteo."""
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return "Nessuna pausa"
        try:
            programs = json.loads(meteo_json)
            paused = [p["name"] for p in programs if not p.get("should_run", True)]
            return f"Pausa: {', '.join(paused)}" if paused else "Attivo"
        except (json.JSONDecodeError, KeyError):
            return "Sconosciuto"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return {}
        try:
            return {"programs": json.loads(meteo_json)}
        except json.JSONDecodeError:
            return {}

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)
