"""
Rain Vision Sensor Entities
============================
Defines all sensor entities for the Rain Vision integration.

Sensors are created dynamically from the hardware and programs
discovered during the first coordinator refresh.

Sensor types:
  RainVisionCloudBatterySensor        — battery % of a Nuvola Vision hub
  RainVisionDeviceBatterySensor       — battery % of a Pure Vision controller
  RainVisionDeviceOnlineSensor        — online/offline status of a device
  RainVisionActiveProgramsSensor      — which programs (A–H) are enabled
  RainVisionMeteoPauseSensor          — current meteo-pause state
  RainVisionProgramDetailSensor       — next start time + full schedule summary
  RainVisionProgramZoneDurationSensor — duration of one zone in one program
  RainVisionProgramTimeSlotSensor     — one start-time slot (0–5) of a program
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

            # One summary sensor + one duration sensor per zone for each program
            programs_data = coordinator.programs.get(device_id, [])
            for prog_info in device.get("fullprogramnames", []):
                letter = prog_info.get("program_progressive", "")
                label  = prog_info.get("custom_name") or prog_info.get("default_name", letter)

                entities.append(
                    RainVisionProgramDetailSensor(coordinator, cloud_id, device_id, letter, label)
                )

                prog_data = next((p for p in programs_data if p.get("name") == letter), None)
                if prog_data:
                    # One duration sensor per zone in this program
                    for zone in prog_data.get("zones", []):
                        entities.append(
                            RainVisionProgramZoneDurationSensor(
                                coordinator, cloud_id, device_id,
                                letter, label,
                                zone_id=zone.get("id"),
                                zone_name=zone.get("name", f"Zone {zone.get('id')}"),
                            )
                        )
                    # One time-slot sensor per slot in this program (up to 6)
                    for time_index, _ in enumerate(prog_data.get("times", [])):
                        entities.append(
                            RainVisionProgramTimeSlotSensor(
                                coordinator, cloud_id, device_id,
                                letter, label,
                                time_index=time_index,
                            )
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
        prog = self._program_data
        if not prog:
            return {}

        active_times   = [t["time"] for t in prog.get("times", []) if t.get("active")]
        total_seconds  = 0
        zones          = []
        for z in prog.get("zones", []):
            dur_s = z.get("duration", 0)
            total_seconds += dur_s
            zones.append({
                "name":             z.get("name"),
                "id":               z.get("id"),
                "duration_seconds": dur_s,
                "duration_minutes": round(dur_s / 60, 1),
                "active":           dur_s > 0,
            })

        weekdays = [d["name"] for d in prog.get("weekdays", []) if d.get("isChecked")]
        try:
            cycle_hours: int | None = int(prog.get("cycle", 0))
        except (TypeError, ValueError):
            cycle_hours = None

        return {
            "active_times":           active_times,
            "zones":                  zones,
            "total_duration_minutes": round(total_seconds / 60, 1),
            "weekdays":               weekdays or None,
            "cycle_hours":            cycle_hours,
            "type":                   prog.get("type"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionProgramZoneDurationSensor(CoordinatorEntity, SensorEntity):
    """Duration sensor for one zone within one irrigation program.

    Created for every (program letter × zone) combination found in
    GetDeviceProgramList. With 4 zones and 4 programs this produces
    16 sensors per Pure Vision device.

    State: duration in minutes (float, e.g. 15.0). Zero means the zone
    is not irrigated in this program.
    Extra attributes: duration_seconds, active flag, zone_id, program info.
    """

    _attr_icon                       = "mdi:timer-outline"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class                = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        program_name: str,
        program_label: str,
        zone_id: int,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._program_name   = program_name
        self._program_label  = program_label
        self._zone_id        = zone_id
        self._zone_name      = zone_name
        self._attr_unique_id = f"device_{device_id}_prog_{program_name}_zone_{zone_id}_duration"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _zone_data(self) -> dict:
        """Return the zone dict for this sensor's (program, zone_id) pair."""
        for p in self.coordinator.programs.get(self._device_id, []):
            if p.get("name") == self._program_name:
                for z in p.get("zones", []):
                    if z.get("id") == self._zone_id:
                        return z
        return {}

    @property
    def name(self) -> str:
        return (
            f"{self._device.get('name', 'Device')} "
            f"Prog {self._program_name} {self._zone_name} Duration"
        )

    @property
    def native_value(self) -> float | None:
        zone = self._zone_data
        return round(zone.get("duration", 0) / 60, 1) if zone else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self._zone_data
        if not zone:
            return {}
        dur_s = zone.get("duration", 0)
        return {
            "duration_seconds": dur_s,
            "duration_minutes": round(dur_s / 60, 1),
            "active":           dur_s > 0,
            "zone_id":          self._zone_id,
            "program":          self._program_name,
            "program_label":    self._program_label,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionProgramTimeSlotSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing a single start-time slot within a program.

    Each program has up to 6 time slots (index 0–5). This sensor exposes
    one slot, showing its configured time as the state and whether it is
    active as an attribute.

    State: time string 'HH:MM' if set, otherwise 'Not set'.
    Extra attributes:
      active      — whether this slot is enabled
      time_index  — slot position (0–5)
      program     — program letter ('A'–'H')
      program_label — human-readable program name
      hidden      — whether the slot is hidden in the app UI
    """

    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        program_name: str,
        program_label: str,
        time_index: int,
    ) -> None:
        """Initialise the time slot sensor.

        Args:
            coordinator:   Shared data coordinator.
            cloud_id:      ID of the parent Nuvola hub.
            device_id:     ID of the Pure Vision device.
            program_name:  Program letter ('A'–'H').
            program_label: Human-readable program name (e.g. 'Prato').
            time_index:    Slot index (0–5).
        """
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._program_name   = program_name
        self._program_label  = program_label
        self._time_index     = time_index
        self._attr_unique_id = (
            f"device_{device_id}_program_{program_name}_time_{time_index}"
        )

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _time_data(self) -> dict:
        """Return the time slot dict for this sensor, or {}."""
        for p in self.coordinator.programs.get(self._device_id, []):
            if p.get("name") == self._program_name:
                times = p.get("times", [])
                if self._time_index < len(times):
                    return times[self._time_index]
        return {}

    @property
    def name(self) -> str:
        device_name = self._device.get("name", "Device")
        return (
            f"{device_name} Prog {self._program_name} "
            f"({self._program_label}) Time {self._time_index + 1}"
        )

    @property
    def native_value(self) -> str:
        """Return the start time string ('HH:MM'), or 'Not set' if empty."""
        t = self._time_data
        return t.get("time") or "Not set"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all fields of the time slot object."""
        t = self._time_data
        if not t:
            return {}
        return {
            "active":        t.get("active", False),
            "time_index":    self._time_index,
            "program":       self._program_name,
            "program_label": self._program_label,
            "hidden":        t.get("hidden", False),
            "records":       t.get("records"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)
