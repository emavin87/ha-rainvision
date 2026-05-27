"""
Rain Vision Switch Entities
=============================
This module defines all switch entities exposed by the Rain Vision integration.

Switches allow the user to control irrigation directly from Home Assistant:
either start/stop manual irrigation on a specific zone, or enable/disable
a scheduled irrigation program.

Switch types:
    - RainVisionZoneSwitch    : Manually start/stop irrigation on a single zone.
                                Uses optimistic state while waiting for the next
                                coordinator poll to confirm the actual state.
    - RainVisionProgramSwitch : Enable or disable a scheduled program (A-H).
                                State is read from the 'active_programs' field
                                returned by the API.

Both switch types trigger a coordinator refresh after sending a command so
that the UI reflects the latest device state as quickly as possible.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RainVisionApi
from .const import DOMAIN, MANUFACTURER, MODEL_DEVICE, DEFAULT_MANUAL_DURATION
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all Rain Vision switch entities for a config entry.

    Creates one RainVisionZoneSwitch per zone per device, and one
    RainVisionProgramSwitch per program per device, based on the
    hardware configuration discovered by the coordinator.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register new entities with HA.
    """
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []

    for cloud_id, cloud in coordinator.clouds.items():
        for device in cloud.get("devices", []):
            device_id = device["id"]

            # Build a zone_number → zone_name lookup from the device data
            zone_names = {
                z["zone_progressive"]: (
                    z.get("custom_name") or z.get("default_name", f"Zone {z['zone_progressive']}")
                )
                for z in device.get("zonenames", [])
            }

            # Create one switch per zone (number of zones from devicetype)
            num_zones = device.get("devicetype", {}).get("zones", 0)
            for zone_num in range(1, num_zones + 1):
                zone_name = zone_names.get(zone_num, f"Zone {zone_num}")
                entities.append(
                    RainVisionZoneSwitch(coordinator, cloud_id, device_id, zone_num, zone_name)
                )

            # Create one switch per program (A-H, or whatever is configured)
            for prog in device.get("fullprogramnames", []):
                letter = prog.get("program_progressive", "")
                label = prog.get("custom_name") or prog.get("default_name", f"Program {letter}")
                entities.append(
                    RainVisionProgramSwitch(coordinator, cloud_id, device_id, letter, label)
                )

    async_add_entities(entities)


def _device_device_info(device: dict, cloud: dict) -> DeviceInfo:
    """Build a DeviceInfo object for a Pure Vision irrigation controller.

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


class RainVisionZoneSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to manually start or stop irrigation on a single zone.

    Turning this switch ON sends a ManualStart command for the zone
    with the default duration (DEFAULT_MANUAL_DURATION minutes).
    Turning it OFF sends a ManualStop command, which stops all
    manual irrigation on the device.

    State management:
        The switch uses a two-layer state approach:
        1. Optimistic: on turn_on/turn_off, the local _is_on flag is updated
           immediately so the UI reflects the change without waiting for the
           next poll cycle.
        2. Real: on every coordinator poll, the 'manual' hex string from the
           device data is decoded to determine the true zone state. If decoding
           succeeds, it overrides the optimistic state.

    Extra attributes: zone number, cloud/device ids, default duration.
    Device: The Pure Vision controller.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:sprinkler"

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        zone: int,
        zone_name: str,
    ) -> None:
        """Initialize the zone switch.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub.
            device_id: The id of the Pure Vision device.
            zone: Zone number (1-based, e.g. 1 for zone 1).
            zone_name: Human-readable zone name (e.g. 'Prato 1').
        """
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._zone = zone
        self._zone_name = zone_name
        self._attr_unique_id = f"device_{device_id}_zone_{zone}"
        # Optimistic local state used between command and next poll
        self._is_on: bool = False

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
        device_name = self._device.get("name", "Device")
        return f"{device_name} {self._zone_name}"

    @property
    def is_on(self) -> bool:
        """Return True if this zone is currently irrigating.

        Attempts to decode the 'manual' hex string from the device data.
        Each zone occupies 2 hex characters (1 byte) in the string,
        starting at offset zone*2. A non-zero byte means the zone is active.
        Falls back to the optimistic _is_on flag if decoding fails.
        """
        manual_hex = self._device.get("manual", "")
        if manual_hex:
            try:
                offset = self._zone * 2
                if len(manual_hex) >= offset + 2:
                    byte_val = int(manual_hex[offset: offset + 2], 16)
                    return byte_val > 0
            except ValueError:
                pass
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return zone metadata for use in automations and the UI."""
        return {
            "zone_number": self._zone,
            "cloud_id": self._cloud_id,
            "device_id": self._device_id,
            "default_duration_minutes": DEFAULT_MANUAL_DURATION,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start manual irrigation on this zone.

        Sends ManualStart to the API, updates the optimistic state,
        then requests a coordinator refresh to confirm the real state.
        An optional 'duration' kwarg overrides the default duration.
        """
        duration = kwargs.get("duration", DEFAULT_MANUAL_DURATION)
        success = await self.coordinator.api.manual_start_zone(
            self._cloud_id, self._device_id, self._zone, duration
        )
        if success:
            self._is_on = True
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop manual irrigation on this device.

        Sends ManualStop (stops all manual zones on the device),
        updates the optimistic state, then requests a coordinator refresh.
        """
        success = await self.coordinator.api.manual_stop(self._cloud_id, self._device_id)
        if success:
            self._is_on = False
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)


class RainVisionProgramSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable or disable a scheduled irrigation program (A-H).

    Turning this switch ON enables the program so it runs according to
    its configured schedule. Turning it OFF disables the program without
    modifying its configuration.

    State is read from the 'active_programs' field in the device data
    (e.g. '[A,B,C,D]'). The program letter of this switch is checked
    against that list.

    Extra attributes: meteo pause info for this specific program
    (whether weather conditions would prevent it from running).
    Device: The Pure Vision controller.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        program: str,
        program_name: str,
    ) -> None:
        """Initialize the program switch.

        Args:
            coordinator: The shared data coordinator.
            cloud_id: The id of the parent Nuvola hub.
            device_id: The id of the Pure Vision device.
            program: Program letter ('A' through 'H').
            program_name: Human-readable program name (e.g. 'Prato').
        """
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._program = program
        self._program_name = program_name
        self._attr_unique_id = f"device_{device_id}_program_{program}"

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
        device_name = self._device.get("name", "Device")
        return f"{device_name} Program {self._program} - {self._program_name}"

    @property
    def is_on(self) -> bool:
        """Return True if this program letter appears in active_programs."""
        active_raw = self._device.get("active_programs", "")
        active_letters = set(active_raw.strip("[]").split(","))
        return self._program in active_letters

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return meteo pause info for this program.

        Attributes include:
            should_run: whether the program would run given current weather
            pop: probability of precipitation
            rain: forecasted rain amount
            temp: forecasted temperature
        """
        meteo_json = self._device.get("meteo_pause_json", "[]")
        try:
            programs = json.loads(meteo_json)
            for p in programs:
                if p.get("name") == self._program:
                    return {
                        "should_run": p.get("should_run", True),
                        "pop": p.get("pop"),
                        "rain": p.get("rain"),
                        "temp": p.get("temp"),
                    }
        except (json.JSONDecodeError, TypeError):
            pass
        return {}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable this irrigation program.

        Calls SetProgramActive with active=True, then requests a refresh.
        """
        await self.coordinator.api.set_program_active(
            self._cloud_id, self._device_id, self._program, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable this irrigation program.

        Calls SetProgramActive with active=False, then requests a refresh.
        """
        await self.coordinator.api.set_program_active(
            self._cloud_id, self._device_id, self._program, False
        )
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)
