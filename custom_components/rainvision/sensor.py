"""
Rain Vision Sensor Entities
============================
Defines all sensor entities for the Rain Vision integration.

Sensors are created dynamically from the hardware and programs
discovered during the first coordinator refresh.

Sensor types:
  RainVisionCloudBatterySensor  -- battery % of a Nuvola Vision hub
  RainVisionDeviceBatterySensor -- battery % of a Pure Vision controller
  RainVisionDeviceOnlineSensor  -- online/offline status of a device
  RainVisionActiveProgramsSensor -- which programs (A-H) are enabled
  RainVisionMeteoPauseSensor    -- current meteo-pause state
  RainVisionProgramDetailSensor -- one sensor per program; state = next active start time.
                                   All program data exposed as flat extra_state_attributes:
                                   times_N_time/active/hidden, zones_N_id/name/duration_*,
                                   weekdays_N_name/index/is_checked, type/cycle/active/even,
                                   total_duration_minutes
"""
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
from homeassistant.const import PERCENTAGE
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
    """Set up all Rain Vision sensor entities for a config entry.

    Iterates over discovered clouds, devices and programs to create
    the appropriate sensor instances dynamically.

    Args:
        hass:               Home Assistant instance.
        entry:              Config entry being set up.
        async_add_entities: Callback to register entities with HA.
    """
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for cloud_id, cloud in coordinator.clouds.items():
        entities.append(RainVisionCloudBatterySensor(coordinator, cloud_id))

        for device in cloud.get("devices", []):
            device_id = device["id"]
            entities.append(RainVisionDeviceBatterySensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionDeviceOnlineSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionActiveProgramsSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionMeteoPauseSensor(coordinator, cloud_id, device_id))

            # One sensor per program -- all data exposed as flat attributes
            for prog_info in device.get("fullprogramnames", []):
                letter = prog_info.get("program_progressive", "")
                label  = prog_info.get("custom_name") or prog_info.get("default_name", letter)
                entities.append(
                    RainVisionProgramDetailSensor(coordinator, cloud_id, device_id, letter, label)
                )

    async_add_entities(entities)


# ── Device info helpers ───────────────────────────────────────────────────────

def _cloud_info(cloud: dict) -> DeviceInfo:
    """Build DeviceInfo for a Nuvola Vision hub."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"cloud_{cloud['id']}")},
        name=cloud.get("name", f"Nuvola {cloud['id']}"),
        manufacturer=MANUFACTURER,
        model=MODEL_CLOUD,
        sw_version=cloud.get("firmwarecloud", {}).get("name"),
    )


def _device_info(device: dict, cloud: dict) -> DeviceInfo:
    """Build DeviceInfo for a Pure Vision controller, linked to its parent hub."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"device_{device['id']}")},
        name=device.get("name", f"Device {device['id']}"),
        manufacturer=MANUFACTURER,
        model=device.get("devicetype", {}).get("name", MODEL_DEVICE),
        sw_version=device.get("firmware", {}).get("name"),
        via_device=(DOMAIN, f"cloud_{cloud['id']}"),
    )


# ── Sensor classes ────────────────────────────────────────────────────────────

class RainVisionCloudBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery level sensor for a Nuvola Vision hub.

    Reads cloud['battery'] from the coordinator's clouds dict.
    State: integer percentage (0–100).
    """

    _attr_device_class              = SensorDeviceClass.BATTERY
    _attr_state_class               = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id         = cloud_id
        self._attr_unique_id   = f"cloud_{cloud_id}_battery"

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Battery"

    @property
    def native_value(self) -> int | None:
        return self._cloud.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_info(self._cloud)


class RainVisionDeviceBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery level sensor for a Pure Vision irrigation controller.

    Reads device['battery'] updated from the real-time nuvola/device response.
    State: integer percentage (0–100).
    """

    _attr_device_class              = SensorDeviceClass.BATTERY
    _attr_state_class               = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_battery"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Battery"

    @property
    def native_value(self) -> int | None:
        # Prefer the battery value from the real-time response (more up-to-date)
        rt = self.coordinator.realtime.get(self._device_id, {})
        rt_battery = rt.get("data", {}).get("status", {}).get("battery")
        return rt_battery if rt_battery is not None else self._device.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionDeviceOnlineSensor(CoordinatorEntity, SensorEntity):
    """Online/offline status sensor for a Pure Vision controller.

    State: 'Online' or 'Offline'.
    Extra attributes: last_update timestamp from nuvola/device.
    """

    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_online"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Status"

    @property
    def native_value(self) -> str:
        return "Online" if self._device.get("online") else "Offline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rt = self.coordinator.realtime.get(self._device_id, {})
        return {
            "last_update": rt.get("timestamp"),
            "next_update": rt.get("next_update"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionActiveProgramsSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing which irrigation programs are currently enabled.

    Reads device['active_programs'] (e.g. '[A,B,C,D]').
    State: comma-separated active letters (e.g. 'A, B, D').
    Extra attributes: per-program name and active flag.
    """

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_active_programs"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Active Programs"

    @property
    def native_value(self) -> str | None:
        raw = self._device.get("active_programs", "")
        return raw.strip("[]").replace(",", ", ") if raw else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose per-program name and active flag (program_A, program_A_active, ...)."""
        device         = self._device
        active_raw     = device.get("active_programs", "")
        active_letters = set(active_raw.strip("[]").split(","))
        attrs: dict[str, Any] = {}
        for prog in device.get("fullprogramnames", []):
            letter = prog.get("program_progressive", "")
            label  = prog.get("custom_name") or prog.get("default_name", letter)
            attrs[f"program_{letter}"]        = label
            attrs[f"program_{letter}_active"] = letter in active_letters
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionMeteoPauseSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing whether a weather-based pause is in effect.

    Reads device['meteo_pause_json'] to determine which programs are
    currently paused due to rain or adverse weather forecasts.

    State: 'Active', 'Pause: A, B', or 'Unknown'.
    Extra attributes: full meteo pause data per program.
    """

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_meteo_pause"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Meteo Pause"

    @property
    def native_value(self) -> str:
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return "No pause"
        try:
            programs = json.loads(meteo_json)
            paused   = [p["name"] for p in programs if not p.get("should_run", True)]
            return f"Pause: {', '.join(paused)}" if paused else "Active"
        except (json.JSONDecodeError, KeyError):
            return "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return raw meteo pause data including pop, rain, temp per program."""
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return {}
        try:
            return {"programs": json.loads(meteo_json)}
        except json.JSONDecodeError:
            return {}

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionProgramDetailSensor(CoordinatorEntity, SensorEntity):
    """Summary sensor for a single irrigation program (A–H).

    State: next active start time ('HH:MM') or 'Inactive'.
    Extra attributes:
      active_times          — list of enabled start time strings
      zones                 — list of {name, id, duration_seconds, duration_minutes, active}
      total_duration_minutes — sum of all zone durations in the program
      weekdays              — enabled weekday names, or null for cycle-based programs
      cycle_hours           — repeat frequency in hours
      type                  — schedule type ('cycle' etc.)
    """

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        program_name: str,
        program_label: str,
    ) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._program_name   = program_name
        self._program_label  = program_label
        self._attr_unique_id = f"device_{device_id}_program_detail_{program_name}"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _program_data(self) -> dict:
        """Return the program dict for this sensor's letter, or {}."""
        for p in self.coordinator.programs.get(self._device_id, []):
            if p.get("name") == self._program_name:
                return p
        return {}

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Program {self._program_name} ({self._program_label})"

    @property
    def native_value(self) -> str:
        prog = self._program_data
        if not prog:
            return "Unknown"
        for t in prog.get("times", []):
            if t.get("active"):
                return t.get("time", "Inactive")
        return "Inactive"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all program data as flat key-value attributes.

        Attribute naming conventions:
          times_N_time, times_N_active, times_N_hidden     -- start-time slots (N=0..5)
          zones_N_id, zones_N_name, zones_N_progressive,
          zones_N_duration_seconds, zones_N_duration_minutes,
          zones_N_active                                    -- zone durations (N=0..3)
          weekdays_N_name, weekdays_N_index,
          weekdays_N_is_checked                             -- weekday schedule (N=0..6)
          type, cycle, active, even                        -- program metadata
          total_duration_minutes                           -- sum of all zone durations
        """
        prog = self._program_data
        if not prog:
            return {}

        attrs: dict[str, Any] = {}

        # Program metadata
        attrs["type"]   = prog.get("type")
        attrs["cycle"]  = prog.get("cycle")
        attrs["active"] = prog.get("active")
        attrs["even"]   = prog.get("even")

        # Start-time slots: times_N_time, times_N_active, times_N_hidden
        for i, t in enumerate(prog.get("times", [])):
            attrs[f"times_{i}_time"]   = t.get("time")
            attrs[f"times_{i}_active"] = t.get("active", False)
            attrs[f"times_{i}_hidden"] = t.get("hidden", False)

        # Zones: zones_N_id, zones_N_name, zones_N_duration_seconds/minutes, zones_N_active
        total_seconds = 0
        for i, z in enumerate(prog.get("zones", [])):
            dur_s = z.get("duration", 0)
            total_seconds += dur_s
            attrs[f"zones_{i}_id"]               = z.get("id")
            attrs[f"zones_{i}_progressive"]       = z.get("progressive")
            attrs[f"zones_{i}_name"]              = z.get("name")
            attrs[f"zones_{i}_duration_seconds"]  = dur_s
            attrs[f"zones_{i}_duration_minutes"]  = round(dur_s / 60, 1)
            attrs[f"zones_{i}_active"]            = dur_s > 0

        attrs["total_duration_minutes"] = round(total_seconds / 60, 1)

        # Weekdays (only populated for weekday-based programs)
        for i, d in enumerate(prog.get("weekdays", [])):
            attrs[f"weekdays_{i}_name"]       = d.get("name")
            attrs[f"weekdays_{i}_index"]      = d.get("index")
            attrs[f"weekdays_{i}_is_checked"] = d.get("isChecked", False)

        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)

