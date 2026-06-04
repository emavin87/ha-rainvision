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
  RainVisionProgramDetailSensor        -- one sensor per program; all data as flat attributes
  RainVisionDeviceLastUpdatedSensor     -- last time device record was updated (updated_at)
  RainVisionCloudLastScannedSensor      -- last BLE scan Nuvola -> Pure Vision (last_scanned_at)
  RainVisionCloudLastConnectionSensor   -- last Nuvola cloud connection (last_connection)
  RainVisionCloudLastPingSensor         -- last Nuvola heartbeat ping (last_ping_at)
  RainVisionRealtimeTimestampSensor     -- timestamp of last nuvola/device response
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
        entities.append(RainVisionCloudLastScannedSensor(coordinator, cloud_id))
        entities.append(RainVisionCloudLastConnectionSensor(coordinator, cloud_id))
        entities.append(RainVisionCloudLastPingSensor(coordinator, cloud_id))

        for device in cloud.get("devices", []):
            device_id = device["id"]
            entities.append(RainVisionDeviceBatterySensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionDeviceOnlineSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionActiveProgramsSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionMeteoPauseSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionDeviceLastUpdatedSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionRealtimeTimestampSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionDeviceRSSISensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionActiveZoneSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionMeteoSensor(coordinator, cloud_id, device_id))

            # One sensor per program -- all data exposed as flat attributes
            for prog_info in device.get("fullprogramnames", []):
                letter = prog_info.get("program_progressive", "")
                label  = prog_info.get("custom_name") or prog_info.get("default_name", letter)
                entities.append(
                    RainVisionProgramDetailSensor(coordinator, cloud_id, device_id, letter, label)
                )

    async_add_entities(entities)

    # BLE peer sensors added dynamically after each coordinator update
    # because scan_peers is populated during the poll cycle, not at startup.
    registered_ble_ids: set = set()

    def _add_ble_peer_sensors() -> None:
        known = set(coordinator.devices.keys())
        new_ents = []
        for dev_id, peer in coordinator.scan_peers.items():
            if dev_id in registered_ble_ids:
                continue
            dt = peer.get("devicetype") or {}
            if dt.get("is_sensor"):
                new_ents.append(RainVisionBLEPeerBatterySensor(coordinator, dev_id))
                new_ents.append(RainVisionBLEPeerRSSISensor(coordinator, dev_id))
            elif dev_id not in known:
                new_ents.append(RainVisionBLEPeerRSSISensor(coordinator, dev_id))
            registered_ble_ids.add(dev_id)
        if new_ents:
            async_add_entities(new_ents)

    _add_ble_peer_sensors()
    coordinator.async_add_listener(_add_ble_peer_sensors)


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
        # Prefer real-time battery from data.status.battery (nuvola/device response)
        # Falls back to device.battery from GetPlaces
        rt = self.coordinator.realtime.get(self._device_id, {})
        rt_battery = (rt.get("data") or {}).get("status", {}).get("battery")
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
        status = (rt.get("data") or {}).get("status", {})
        return {
            "last_update":  rt.get("timestamp"),
            "next_update":  rt.get("next_update"),
            "status_hex":   status.get("status"),
            "pause_hex":    status.get("pause"),
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
        """Return 'Active' if any program is weather-paused, 'Inactive' otherwise."""
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return "Unknown"
        import json
        try:
            items = json.loads(meteo_json) if isinstance(meteo_json, str) else meteo_json
        except (json.JSONDecodeError, TypeError):
            return "Unknown"
        paused = [p["name"] for p in items if not p.get("should_run", True)]
        return "Active" if paused else "Inactive"

    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return meteo pause details per program as flat attributes."""
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return {}
        try:
            items = json.loads(meteo_json) if isinstance(meteo_json, str) else meteo_json
        except (json.JSONDecodeError, TypeError):
            return {}
        attrs = {}
        for p in items:
            name = p.get("name", "?")
            attrs[f"prog_{name}_should_run"]  = p.get("should_run", True)
            attrs[f"prog_{name}_rain"]        = p.get("rain")
            attrs[f"prog_{name}_pop"]         = p.get("pop")
            attrs[f"prog_{name}_temp"]        = p.get("temp")
            attrs[f"prog_{name}_wind"]        = p.get("wind")
            attrs[f"prog_{name}_irrigation_variable"] = p.get("irrigation_variable")
        paused = [p["name"] for p in items if not p.get("should_run", True)]
        attrs["paused_programs"] = paused if paused else []
        return attrs

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
        # "active" field may be absent from GetDeviceProgramList response.
        # Fall back to device["active_programs"] (e.g. "[A,B,C,D]") from GetPlaces.
        # active field may be null/absent in GetDeviceProgramList.
        # Always derive it from active_programs in GetPlaces which is reliable.
        active_raw = self._device.get("active_programs", "")
        active_letters = set(active_raw.strip("[]").split(","))
        attrs["active"] = self._program_name in active_letters
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



# ── Timestamp sensors ─────────────────────────────────────────────────────────

class RainVisionDeviceLastUpdatedSensor(CoordinatorEntity, SensorEntity):
    """Last time the device record was updated in the Rain Vision cloud database.

    Source: devices[0].updated_at from GetPlaces.
    This reflects the last time any property of the device changed in the
    backend, not necessarily the last time it communicated.

    State: ISO 8601 timestamp string.
    """

    _attr_icon        = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_last_updated"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Last Updated"

    @property
    def native_value(self):
        """Return updated_at as a datetime object for HA timestamp device class."""
        from datetime import datetime, timezone
        val = self._device.get("updated_at")
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "description": "Last time the device record was updated in the Rain Vision cloud database",
            "source_field": "devices[0].updated_at",
            "source_api":   "GetPlaces",
            "raw_value":    self._device.get("updated_at"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionCloudLastScannedSensor(CoordinatorEntity, SensorEntity):
    """Last time the Nuvola hub scanned the Pure Vision device via BLE.

    Source: clouds[0].last_scanned_at from GetPlaces.
    This is the most reliable indicator of when fresh device data was
    last retrieved from the Pure Vision controller.

    State: ISO 8601 timestamp string.
    """

    _attr_icon         = "mdi:bluetooth-connect"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._attr_unique_id = f"cloud_{cloud_id}_last_scanned"

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Last Scanned"

    @property
    def native_value(self):
        """Return last_scanned_at as a datetime object."""
        from datetime import datetime, timezone
        val = self._cloud.get("last_scanned_at")
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "description": "Last time the Nuvola hub scanned the Pure Vision device via BLE",
            "source_field": "clouds[0].last_scanned_at",
            "source_api":   "GetPlaces",
            "raw_value":    self._cloud.get("last_scanned_at"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_info(self._cloud)


class RainVisionCloudLastConnectionSensor(CoordinatorEntity, SensorEntity):
    """Last time the Nuvola hub connected to the Rain Vision cloud.

    Source: clouds[0].last_connection from GetPlaces.
    Useful to detect if the hub has gone offline or lost internet connectivity.

    State: ISO 8601 timestamp string.
    """

    _attr_icon         = "mdi:cloud-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._attr_unique_id = f"cloud_{cloud_id}_last_connection"

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Last Connection"

    @property
    def native_value(self):
        from datetime import datetime
        val = self._cloud.get("last_connection")
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "description": "Last time the Nuvola hub connected to the Rain Vision cloud",
            "source_field": "clouds[0].last_connection",
            "source_api":   "GetPlaces",
            "raw_value":    self._cloud.get("last_connection"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_info(self._cloud)


class RainVisionCloudLastPingSensor(CoordinatorEntity, SensorEntity):
    """Last time the Nuvola hub sent a ping to the Rain Vision cloud.

    Source: clouds[0].last_ping_at from GetPlaces.
    The ping is a lightweight heartbeat signal. If this timestamp is stale,
    the hub may have lost connectivity even if last_connection appears recent.

    State: ISO 8601 timestamp string.
    """

    _attr_icon         = "mdi:heart-pulse"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._attr_unique_id = f"cloud_{cloud_id}_last_ping"

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Last Ping"

    @property
    def native_value(self):
        from datetime import datetime
        val = self._cloud.get("last_ping_at")
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "description": "Last time the Nuvola hub sent a ping to the Rain Vision cloud",
            "source_field": "clouds[0].last_ping_at",
            "source_api":   "GetPlaces",
            "raw_value":    self._cloud.get("last_ping_at"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_info(self._cloud)


class RainVisionRealtimeTimestampSensor(CoordinatorEntity, SensorEntity):
    """Timestamp of the last real-time response from the nuvola/device endpoint.

    Source: data.timestamp from nuvola/device API.
    This is the freshest available timestamp — it reflects when the Nuvola
    hub last provided a live status snapshot of the Pure Vision device.

    State: ISO 8601 timestamp string.
    """

    _attr_icon         = "mdi:antenna"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_realtime_timestamp"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Realtime Timestamp"

    @property
    def native_value(self):
        from datetime import datetime
        rt  = self.coordinator.realtime.get(self._device_id, {})
        # timestamp is at root level: {"timestamp": "2026-05-30T19:00:51.185141Z", ...}
        val = rt.get("timestamp")
        if not val:
            return None
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        rt = self.coordinator.realtime.get(self._device_id, {})
        status = (rt.get("data") or {}).get("status", {})
        return {
            "description":  "Timestamp of the last real-time response from nuvola/device",
            "source_field": "timestamp",
            "source_api":   "nuvola/device",
            "raw_value":    rt.get("timestamp"),
            "next_update":  rt.get("next_update"),
            "battery":      status.get("battery"),
            "status_hex":   status.get("status"),
            "pause_hex":    status.get("pause"),
            "last_poll_at": self.coordinator.last_poll_at,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionDeviceRSSISensor(CoordinatorEntity, SensorEntity):
    """BLE signal strength (RSSI) sensor for a Pure Vision device.

    Reads the 'rssi' field from the nuvola/scan/full response, which
    gives the BLE signal strength between the Nuvola hub and the device.
    Higher values indicate a stronger signal.

    Source: peers[N].rssi from POST /api/v5/nuvola/scan/full.

    State: integer RSSI value (e.g. 88).
    Extra attributes:
      description  — explains the field
      source_api   — nuvola/scan/full
      battery      — battery level from scan (may differ slightly from GetPlaces)
      fw           — firmware version from scan
      paired       — whether the device is paired to the Nuvola hub
      mdata        — raw BLE manufacturer data hex string
    """

    _attr_icon                       = "mdi:bluetooth-audio"
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class                = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_rssi"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _peer(self) -> dict:
        """Return the scan peer dict for this device, or {}."""
        return self.coordinator.scan_peers.get(self._device_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} BLE RSSI"

    @property
    def native_value(self) -> int | None:
        """Return RSSI value from nuvola/scan/full, or None if unavailable."""
        return self._peer.get("rssi")

    @property
    def extra_state_attributes(self) -> dict:
        peer = self._peer
        if not peer:
            return {}
        return {
            "description": "BLE signal strength between Nuvola hub and Pure Vision device",
            "source_api":  "nuvola/scan/full",
            "battery":     peer.get("battery"),
            "fw":          peer.get("fw"),
            "paired":      peer.get("paired"),
            "mdata":       peer.get("mdata"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


# ── Generic BLE peer sensors (for all devices found via nuvola/scan/full) ────
# Created for every device in coordinator.scan_peers, covering Pure Vision,
# Acqua Vision, and any future Rain Vision BLE device visible to the Nuvola hub.

class RainVisionBLEPeerBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery sensor for any BLE peer device discovered via nuvola/scan/full.

    Created for devices found in the scan that are NOT already covered by
    the main device battery sensor (i.e. sensor-type devices like Acqua Vision).
    The battery value from the scan may be more up-to-date than GetPlaces.

    State: integer battery percentage (0-100).
    """

    _attr_device_class               = SensorDeviceClass.BATTERY
    _attr_state_class                = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: RainVisionCoordinator, device_id: int) -> None:
        super().__init__(coordinator)
        self._device_id      = device_id
        self._attr_unique_id = f"ble_peer_{device_id}_battery"

    @property
    def _peer(self) -> dict:
        return self.coordinator.scan_peers.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._peer.get("cloud_id"), {})

    @property
    def name(self) -> str:
        dev = self._peer.get("device") or {}
        return f"{dev.get('name', f'BLE Device {self._device_id}')} Battery"

    @property
    def native_value(self) -> int | None:
        return self._peer.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        peer = self._peer
        dev  = peer.get("device") or {}
        dt   = peer.get("devicetype") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, f"ble_peer_{self._device_id}")},
            name=dev.get("name", f"BLE Device {self._device_id}"),
            manufacturer=MANUFACTURER,
            model=dt.get("name", "Rain Vision Device"),
            sw_version=peer.get("fw"),
            via_device=(DOMAIN, f"cloud_{peer.get('cloud_id')}"),
        )


class RainVisionBLEPeerRSSISensor(CoordinatorEntity, SensorEntity):
    """BLE RSSI sensor for any device discovered via nuvola/scan/full.

    Provides the BLE signal strength between the Nuvola hub and the device.
    Created for ALL scan peers — Pure Vision, Acqua Vision, and any other
    BLE device in range of the hub.

    State: integer RSSI value in dBm (e.g. 88). Higher = stronger signal.
    Extra attributes: paired, fw, mdata, device_name, device_type.
    """

    _attr_icon                       = "mdi:bluetooth-audio"
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class                = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RainVisionCoordinator, device_id: int) -> None:
        super().__init__(coordinator)
        self._device_id      = device_id
        self._attr_unique_id = f"ble_peer_{device_id}_rssi"

    @property
    def _peer(self) -> dict:
        return self.coordinator.scan_peers.get(self._device_id, {})

    @property
    def name(self) -> str:
        dev = self._peer.get("device") or {}
        return f"{dev.get('name', f'BLE Device {self._device_id}')} BLE RSSI"

    @property
    def native_value(self) -> int | None:
        return self._peer.get("rssi")

    @property
    def extra_state_attributes(self) -> dict:
        peer = self._peer
        dev  = peer.get("device") or {}
        dt   = peer.get("devicetype") or {}
        return {
            "description": "BLE signal strength between Nuvola hub and device",
            "source_api":  "nuvola/scan/full",
            "device_name": dev.get("name"),
            "device_type": dt.get("name"),
            "puid":        dev.get("puid"),
            "paired":      peer.get("paired"),
            "fw":          peer.get("fw"),
            "mdata":       peer.get("mdata"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        peer = self._peer
        dev  = peer.get("device") or {}
        dt   = peer.get("devicetype") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, f"ble_peer_{self._device_id}")},
            name=dev.get("name", f"BLE Device {self._device_id}"),
            manufacturer=MANUFACTURER,
            model=dt.get("name", "Rain Vision Device"),
            sw_version=peer.get("fw"),
            via_device=(DOMAIN, f"cloud_{peer.get('cloud_id')}"),
        )


class RainVisionActiveZoneSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing which zone is currently irrigating.

    Decodes the 'status' hex string from the nuvola/device real-time response.
    The active zone bitmask is encoded in bytes 4-5 (offset 8-9) of the hex string:

      Bitmask -> Zone
        0x01  -> Zone 1 (Lawn 1 / Prato 1)
        0x02  -> Zone 2 (Lawn 2 / Prato 2)
        0x04  -> Zone 3 (Plants / Piante)
        0x08  -> Zone 4 (Garden / Orto)
        0x00  -> No zone active (idle)

    State: zone name (e.g. "Prato 1") or "Idle" when no zone is running.
    Extra attributes:
      zone_bitmask     — raw bitmask value (int)
      zone_progressive — progressive zone index (1–4) or None
      status_hex       — full raw status hex string
    """

    _attr_icon = "mdi:sprinkler-fire"

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_active_zone"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _status_hex(self) -> str:
        rt = self.coordinator.realtime.get(self._device_id, {})
        return (rt.get("data") or {}).get("status", {}).get("status", "") or ""

    @property
    def _zone_bitmask(self) -> int:
        """Extract the active zone bitmask from bytes 4-5 of the status hex string."""
        hex_str = self._status_hex
        if len(hex_str) < 10:
            return 0
        try:
            return int(hex_str[8:10], 16)
        except ValueError:
            return 0

    @property
    def _zone_name(self) -> str:
        """Return the display name of the active zone from coordinator zone data."""
        bitmask = self._zone_bitmask
        if bitmask == 0:
            return "Idle"
        # Map bitmask to progressive index
        bitmask_to_progressive = {0x01: 1, 0x02: 2, 0x04: 3, 0x08: 4}
        progressive = bitmask_to_progressive.get(bitmask)
        if progressive is None:
            return f"Zone bitmask 0x{bitmask:02x}"
        # Look up the custom name from zone names
        for z in self._device.get("zonenames", []):
            if z.get("zone_progressive") == progressive:
                return z.get("custom_name") or z.get("default_name", f"Zone {progressive}")
        return f"Zone {progressive}"

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Active Zone"

    @property
    def native_value(self) -> str:
        return self._zone_name

    @property
    def extra_state_attributes(self) -> dict:
        bitmask = self._zone_bitmask
        bitmask_to_progressive = {0x01: 1, 0x02: 2, 0x04: 3, 0x08: 4}
        return {
            "zone_bitmask":     bitmask,
            "zone_progressive": bitmask_to_progressive.get(bitmask),
            "status_hex":       self._status_hex,
            "last_poll_at":     self.coordinator.last_poll_at,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionMeteoSensor(CoordinatorEntity, SensorEntity):
    """Current weather conditions sensor for the Nuvola hub location.

    Reads the 'meteo' object nested inside device.cloud from the
    nuvola/device real-time response. Provides current weather data
    (temperature, humidity, wind, etc.) as a single sensor with all
    fields exposed as flat attributes.

    Source: device.cloud.meteo from POST /api/v5/nuvola/device.

    State: current temperature in °C (main_temp).
    Extra attributes: full meteo object fields.
    """

    _attr_icon                       = "mdi:weather-partly-cloudy"
    _attr_native_unit_of_measurement = "°C"
    _attr_device_class               = SensorDeviceClass.TEMPERATURE
    _attr_state_class                = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int, device_id: int) -> None:
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._attr_unique_id = f"device_{device_id}_meteo"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _meteo(self) -> dict:
        """Return the meteo dict from the realtime response, or {}."""
        rt = self.coordinator.realtime.get(self._device_id, {})
        return (rt.get("device") or {}).get("cloud", {}).get("meteo") or {}

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Meteo"

    @property
    def native_value(self) -> float | None:
        """Return current temperature as the sensor state."""
        val = self._meteo.get("main_temp")
        return round(float(val), 1) if val is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        m = self._meteo
        if not m:
            return {}
        return {
            # Temperature
            "temp":            m.get("main_temp"),
            "temp_min":        m.get("main_temp_min"),
            "temp_max":        m.get("main_temp_max"),
            "feels_like":      m.get("main_feels_like"),
            # Atmosphere
            "humidity":        m.get("main_humidity"),
            "pressure":        m.get("main_pressure"),
            "visibility":      m.get("visibility"),
            # Wind
            "wind_speed":      m.get("wind_speed"),
            "wind_deg":        m.get("wind_deg"),
            "wind_gust":       m.get("wind_gust"),
            # Sky
            "clouds":          m.get("clouds_all"),
            "weather_main":    m.get("weather_main"),
            "description":     m.get("weather_description"),
            "icon":            m.get("weather_icon"),
            "ionic_icon":      m.get("ionic_icon_name"),
            # Timestamps
            "dt":              m.get("dt"),
            "time":            m.get("time"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_info(self._cloud)
