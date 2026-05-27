"""
Rain Vision Sensor Entities
============================
This module defines all sensor entities exposed by the Rain Vision integration.

Each sensor class extends CoordinatorEntity (for automatic state updates
on coordinator polls) and SensorEntity (for the HA sensor platform contract).

Sensors are created dynamically in async_setup_entry based on the devices
and programs discovered during the first coordinator refresh. No sensors
are hard-coded — they reflect whatever hardware and programs are found in
the user's Rain Vision account.

Sensor types:
    - RainVisionCloudBatterySensor   : Battery level of a Nuvola hub
    - RainVisionDeviceBatterySensor  : Battery level of a Pure Vision controller
    - RainVisionActiveProgramsSensor : Which programs (A-H) are currently active
    - RainVisionMeteoPauseSensor     : Whether a meteo pause is in effect
    - RainVisionProgramDetailSensor  : Summary of a single program (next start time,
                                       total duration, active zones, cycle info)
    - RainVisionProgramZoneDurationSensor : Duration assigned to one zone in one program
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
    """Set up all Rain Vision sensor entities for a config entry.

    Called by HA when the integration is loaded. Iterates over all clouds
    and devices discovered by the coordinator and creates the appropriate
    sensor instances. Also creates one detail sensor and one zone-duration
    sensor per program per device.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register new entities with HA.
    """
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for cloud_id, cloud in coordinator.clouds.items():
        # One battery sensor per Nuvola hub
        entities.append(RainVisionCloudBatterySensor(coordinator, cloud_id))

        for device in cloud.get("devices", []):
            device_id = device["id"]

            # Battery and status sensors for each Pure Vision device
            entities.append(RainVisionDeviceBatterySensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionActiveProgramsSensor(coordinator, cloud_id, device_id))
            entities.append(RainVisionMeteoPauseSensor(coordinator, cloud_id, device_id))

            # Program detail sensors + per-zone duration sensors
            # One RainVisionProgramDetailSensor per program letter (A-H)
            # One RainVisionProgramZoneDurationSensor per zone per program
            programs_data = coordinator.programs.get(device_id, [])
            for prog_info in device.get("fullprogramnames", []):
                letter = prog_info.get("program_progressive", "")
                label = prog_info.get("custom_name") or prog_info.get("default_name", letter)

                entities.append(
                    RainVisionProgramDetailSensor(coordinator, cloud_id, device_id, letter, label)
                )

                prog_data = next((p for p in programs_data if p.get("name") == letter), None)
                if prog_data:
                    for zone in prog_data.get("zones", []):
                        entities.append(
                            RainVisionProgramZoneDurationSensor(
                                coordinator,
                                cloud_id,
                                device_id,
                                letter,
                                label,
                                zone_id=zone.get("id"),
                                zone_name=zone.get("name", f"Zone {zone.get('id')}"),
                            )
                        )

    async_add_entities(entities)


# ── Device info helpers ───────────────────────────────────────────────────────

def _cloud_device_info(cloud: dict) -> DeviceInfo:
    """Build a DeviceInfo object for a Nuvola Vision hub.

    Used by cloud-level sensors to associate themselves with the
    correct device in the HA device registry.

    Args:
        cloud: Cloud data dict from the coordinator.

    Returns:
        A DeviceInfo instance identifying the Nuvola hub.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"cloud_{cloud['id']}")},
        name=cloud.get("name", f"Nuvola {cloud['id']}"),
        manufacturer=MANUFACTURER,
        model=MODEL_CLOUD,
        sw_version=cloud.get("firmwarecloud", {}).get("name"),
    )


def _device_device_info(device: dict, cloud: dict) -> DeviceInfo:
    """Build a DeviceInfo object for a Pure Vision irrigation controller.

    Links the device to its parent Nuvola hub via via_device, so the
    HA device registry shows the correct hierarchy.

    Args:
        device: Device data dict from the coordinator.
        cloud: Parent cloud data dict (used for via_device linkage).

    Returns:
        A DeviceInfo instance identifying the Pure Vision controller.
    """
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
    """Battery level sensor for a Nuvola Vision cloud hub.

    Reads the 'battery' field from the cloud data dict returned by
    GetPlaces. The Nuvola hub is a mains-powered device but may have
    an internal battery for backup; this sensor reflects that value.

    State: integer percentage (0-100).
    Device: The Nuvola hub identified by cloud_id.
    """

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: RainVisionCoordinator, cloud_id: int) -> None:
        """Initialize the cloud battery sensor.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the Nuvola hub to monitor.
        """
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._attr_unique_id = f"cloud_{cloud_id}_battery"

    @property
    def _cloud(self) -> dict:
        """Return the current cloud data dict from the coordinator."""
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._cloud.get('name', 'Nuvola')} Battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery percentage, or None if unavailable."""
        return self._cloud.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        return _cloud_device_info(self._cloud)


class RainVisionDeviceBatterySensor(CoordinatorEntity, SensorEntity):
    """Battery level sensor for a Pure Vision irrigation controller.

    The Pure Vision is a battery-powered device; this sensor exposes
    the 'battery' field from the device data returned by GetPlaces.
    Monitoring this sensor allows automations to alert when the battery
    is low and irrigation may stop working.

    State: integer percentage (0-100).
    Device: The Pure Vision controller identified by device_id.
    """

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
    ) -> None:
        """Initialize the device battery sensor.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub (for device linking).
            device_id: The id of the Pure Vision device to monitor.
        """
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._attr_unique_id = f"device_{device_id}_battery"

    @property
    def _device(self) -> dict:
        """Return the current device data dict from the coordinator."""
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        """Return the parent cloud data dict from the coordinator."""
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery percentage, or None if unavailable."""
        return self._device.get("battery")

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)


class RainVisionActiveProgramsSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing which irrigation programs are currently enabled.

    Reads the 'active_programs' field from the device data, which is a
    string like '[A,B,C,D]' listing the currently active program letters.

    State: comma-separated string of active program letters (e.g. 'A, B').
    Extra attributes: per-program name and active state for all programs.
    Device: The Pure Vision controller.
    """

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
    ) -> None:
        """Initialize the active programs sensor.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub.
            device_id: The id of the Pure Vision device.
        """
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
        return f"{self._device.get('name', 'Device')} Active Programs"

    @property
    def native_value(self) -> str | None:
        """Return active program letters as a readable string (e.g. 'A, B, D')."""
        raw = self._device.get("active_programs", "")
        return raw.strip("[]").replace(",", ", ") if raw else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-program name and active flag for all programs.

        Attribute keys follow the pattern:
            program_A, program_A_active, program_B, program_B_active, ...
        """
        device = self._device
        active_raw = device.get("active_programs", "")
        active_letters = set(active_raw.strip("[]").split(","))

        programs: dict[str, Any] = {}
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
    """Sensor showing whether a meteo (weather) pause is active.

    Rain Vision can automatically pause irrigation programs when rain
    or adverse weather is forecast. This sensor reads the 'meteo_pause_json'
    field from the device data and reports whether any program is currently
    paused due to weather conditions.

    State: human-readable string ('Active', 'Pause: A, B', or 'Unknown').
    Extra attributes: full meteo pause data per program.
    Device: The Pure Vision controller.
    """

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
    ) -> None:
        """Initialize the meteo pause sensor.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub.
            device_id: The id of the Pure Vision device.
        """
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
        return f"{self._device.get('name', 'Device')} Meteo Pause"

    @property
    def native_value(self) -> str:
        """Return a readable state string indicating which programs are paused.

        Returns 'Active' if no programs are paused, 'Pause: X, Y' if
        some programs are paused, or 'Unknown' if the data cannot be parsed.
        """
        meteo_json = self._device.get("meteo_pause_json")
        if not meteo_json:
            return "No pause"
        try:
            programs = json.loads(meteo_json)
            paused = [p["name"] for p in programs if not p.get("should_run", True)]
            return f"Pause: {', '.join(paused)}" if paused else "Active"
        except (json.JSONDecodeError, KeyError):
            return "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw meteo pause data as a list of program objects."""
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


class RainVisionProgramDetailSensor(CoordinatorEntity, SensorEntity):
    """Summary sensor for a single irrigation program (A-H).

    Reads from the programs dict populated by the coordinator via
    GetDeviceProgramList. Provides the next active start time as the
    main state, plus rich attributes covering all zones, durations,
    weekdays, and cycle frequency.

    State: Next active start time in 'HH:MM' format, or 'Inactive'.
    Extra attributes:
        - active_times: list of enabled start times
        - zones: list of {name, duration_seconds, duration_minutes, active}
        - total_duration_minutes: sum of all zone durations
        - weekdays: list of enabled weekday names (null if cycle-based)
        - cycle_hours: repeat frequency in hours
        - type: schedule type ('cycle' or other)
    Device: The Pure Vision controller.
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
        """Initialize the program detail sensor.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub.
            device_id: The id of the Pure Vision device.
            program_name: Program letter ('A' through 'H').
            program_label: Human-readable program name (e.g. 'Prato').
        """
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._program_name = program_name
        self._program_label = program_label
        self._attr_unique_id = f"device_{device_id}_program_detail_{program_name}"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _program_data(self) -> dict:
        """Return the program dict for this sensor's program letter, or {}."""
        programs = self.coordinator.programs.get(self._device_id, [])
        for p in programs:
            if p.get("name") == self._program_name:
                return p
        return {}

    @property
    def name(self) -> str:
        device_name = self._device.get("name", "Device")
        return f"{device_name} Program {self._program_name} ({self._program_label})"

    @property
    def native_value(self) -> str:
        """Return the first active start time, or 'Inactive' if none are enabled."""
        prog = self._program_data
        if not prog:
            return "Unknown"
        for t in prog.get("times", []):
            if t.get("active"):
                return t.get("time", "Inactive")
        return "Inactive"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full program details as HA state attributes."""
        prog = self._program_data
        if not prog:
            return {}

        active_times = [
            t["time"] for t in prog.get("times", []) if t.get("active")
        ]

        zones = []
        total_seconds = 0
        for z in prog.get("zones", []):
            duration_s = z.get("duration", 0)
            duration_m = round(duration_s / 60, 1)
            total_seconds += duration_s
            zones.append({
                "name": z.get("name"),
                "id": z.get("id"),
                "duration_seconds": duration_s,
                "duration_minutes": duration_m,
                "active": duration_s > 0,
            })

        weekdays = [
            d["name"] for d in prog.get("weekdays", []) if d.get("isChecked")
        ]

        cycle_hours = prog.get("cycle")
        try:
            cycle_hours = int(cycle_hours)
        except (TypeError, ValueError):
            cycle_hours = None

        return {
            "active_times": active_times,
            "zones": zones,
            "total_duration_minutes": round(total_seconds / 60, 1),
            "weekdays": weekdays if weekdays else None,
            "cycle_hours": cycle_hours,
            "type": prog.get("type"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)


class RainVisionProgramZoneDurationSensor(CoordinatorEntity, SensorEntity):
    """Duration sensor for one zone within one irrigation program.

    Created for each (program, zone) combination found in GetDeviceProgramList.
    For example, with 4 zones and 4 programs (A-D), 16 of these sensors
    are created per device.

    Provides the duration assigned to that specific zone in that specific
    program, in minutes. A value of 0 means the zone is not irrigated
    in that program.

    State: float minutes (e.g. 15.0).
    Extra attributes: duration in seconds, active flag, zone id, program info.
    Device: The Pure Vision controller.
    """

    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

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
        """Initialize the program zone duration sensor.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub.
            device_id: The id of the Pure Vision device.
            program_name: Program letter ('A' through 'H').
            program_label: Human-readable program name.
            zone_id: Zone id as used by the API (1, 2, 4, or 8).
            zone_name: Human-readable zone name (e.g. 'Prato 1').
        """
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._program_name = program_name
        self._program_label = program_label
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_unique_id = (
            f"device_{device_id}_program_{program_name}_zone_{zone_id}_duration"
        )

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def _zone_data(self) -> dict:
        """Return the zone dict for this sensor's program+zone combination, or {}."""
        programs = self.coordinator.programs.get(self._device_id, [])
        for p in programs:
            if p.get("name") == self._program_name:
                for z in p.get("zones", []):
                    if z.get("id") == self._zone_id:
                        return z
        return {}

    @property
    def name(self) -> str:
        device_name = self._device.get("name", "Device")
        return f"{device_name} Prog {self._program_name} {self._zone_name} Duration"

    @property
    def native_value(self) -> float | None:
        """Return zone duration in minutes, or None if data is unavailable."""
        zone = self._zone_data
        if not zone:
            return None
        return round(zone.get("duration", 0) / 60, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return duration in both seconds and minutes, plus metadata."""
        zone = self._zone_data
        if not zone:
            return {}
        duration_s = zone.get("duration", 0)
        return {
            "duration_seconds": duration_s,
            "duration_minutes": round(duration_s / 60, 1),
            "active": duration_s > 0,
            "zone_id": self._zone_id,
            "program": self._program_name,
            "program_label": self._program_label,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)
