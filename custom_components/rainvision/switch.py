"""
Rain Vision Switch Entities
============================
Defines switch entities for manual zone control and program enable/disable.

Switch types:
  RainVisionZoneSwitch    — start/stop manual irrigation on one zone.
                            Uses optimistic state between command and next poll.
                            Real state is decoded from the device's 'manual' hex string.
  RainVisionProgramSwitch — enable/disable a scheduled program (A–H).
                            State is read from device['active_programs'].
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

from .const import DOMAIN, MANUFACTURER, MODEL_DEVICE, DEFAULT_MANUAL_DURATION
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rain Vision switch entities.

    Creates one RainVisionZoneSwitch per zone and one
    RainVisionProgramSwitch per program for every discovered device.

    Args:
        hass:               Home Assistant instance.
        entry:              Config entry being set up.
        async_add_entities: Callback to register entities with HA.
    """
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []

    for cloud_id, cloud in coordinator.clouds.items():
        for device in cloud.get("devices", []):
            device_id = device["id"]

            # zone_number → display name lookup
            zone_names = {
                z["zone_progressive"]: (
                    z.get("custom_name") or z.get("default_name", f"Zone {z['zone_progressive']}")
                )
                for z in device.get("zonenames", [])
            }

            num_zones = device.get("devicetype", {}).get("zones", 0)
            for zone_num in range(1, num_zones + 1):
                entities.append(
                    RainVisionZoneSwitch(
                        coordinator, cloud_id, device_id,
                        zone_num, zone_names.get(zone_num, f"Zone {zone_num}"),
                    )
                )

            for prog in device.get("fullprogramnames", []):
                letter = prog.get("program_progressive", "")
                label  = prog.get("custom_name") or prog.get("default_name", f"Program {letter}")
                entities.append(
                    RainVisionProgramSwitch(coordinator, cloud_id, device_id, letter, label)
                )

    async_add_entities(entities)


def _device_info(device: dict, cloud: dict) -> DeviceInfo:
    """Build DeviceInfo for a Pure Vision controller linked to its parent hub."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"device_{device['id']}")},
        name=device.get("name", f"Device {device['id']}"),
        manufacturer=MANUFACTURER,
        model=device.get("devicetype", {}).get("name", MODEL_DEVICE),
        sw_version=device.get("firmware", {}).get("name"),
        via_device=(DOMAIN, f"cloud_{cloud['id']}"),
    )


class RainVisionZoneSwitch(CoordinatorEntity, SwitchEntity):
    """Switch that manually starts or stops irrigation on a single zone.

    ON  → sends ManualStart for this zone with DEFAULT_MANUAL_DURATION minutes.
    OFF → sends ManualStop (stops all manual irrigation on the device).

    State is resolved in priority order:
      1. Real state decoded from the 'manual' hex string in the device data.
         Each zone occupies 2 hex chars at offset zone*2; a non-zero byte
         means the zone is actively irrigating.
      2. Optimistic _is_on flag set immediately after a command is sent,
         used while waiting for the next coordinator poll to confirm the state.

    Extra attributes: zone_number, cloud_id, device_id, default_duration_minutes.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon         = "mdi:sprinkler"

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        zone: int,
        zone_name: str,
    ) -> None:
        """Initialise the zone switch.

        Args:
            coordinator: Shared data coordinator.
            cloud_id:    ID of the parent Nuvola hub.
            device_id:   ID of the Pure Vision device.
            zone:        Zone number (1-based).
            zone_name:   Human-readable zone name (e.g. 'Prato 1').
        """
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._zone           = zone
        self._zone_name      = zone_name
        self._attr_unique_id = f"device_{device_id}_zone_{zone}"
        self._is_on: bool    = False   # optimistic state

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} {self._zone_name}"

    @property
    def is_on(self) -> bool:
        """Decode the 'manual' hex string to determine if this zone is active.

        The manual field is a 64-char hex string. Zone N occupies bytes at
        offset N*2 (0-indexed). A non-zero byte means the zone is running.
        Falls back to the optimistic _is_on flag if decoding fails.
        """
        manual_hex = self._device.get("manual", "")
        if manual_hex:
            try:
                offset = self._zone * 2
                if len(manual_hex) >= offset + 2:
                    return int(manual_hex[offset: offset + 2], 16) > 0
            except ValueError:
                pass
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "zone_number":             self._zone,
            "cloud_id":                self._cloud_id,
            "device_id":               self._device_id,
            "default_duration_minutes": DEFAULT_MANUAL_DURATION,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start manual irrigation on this zone."""
        duration = kwargs.get("duration", DEFAULT_MANUAL_DURATION)
        success  = await self.coordinator.api.manual_start_zone(
            self._cloud_id, self._device_id, self._zone, duration
        )
        if success:
            self._is_on = True
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop all manual irrigation on this device."""
        success = await self.coordinator.api.manual_stop(self._cloud_id, self._device_id)
        if success:
            self._is_on = False
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)


class RainVisionProgramSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable or disable a scheduled irrigation program (A–H).

    ON  → calls SetProgramActive with active=True.
    OFF → calls SetProgramActive with active=False.

    State is read from device['active_programs'] (e.g. '[A,B,C,D]').
    This program's letter is checked against that list on every poll.

    Extra attributes: meteo pause info for this specific program
    (should_run, pop, rain, temp).
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon         = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: RainVisionCoordinator,
        cloud_id: int,
        device_id: int,
        program: str,
        program_name: str,
    ) -> None:
        """Initialise the program switch.

        Args:
            coordinator:  Shared data coordinator.
            cloud_id:     ID of the parent Nuvola hub.
            device_id:    ID of the Pure Vision device.
            program:      Program letter ('A'–'H').
            program_name: Human-readable program name (e.g. 'Prato').
        """
        super().__init__(coordinator)
        self._cloud_id       = cloud_id
        self._device_id      = device_id
        self._program        = program
        self._program_name   = program_name
        self._attr_unique_id = f"device_{device_id}_program_{program}"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        return f"{self._device.get('name', 'Device')} Program {self._program} — {self._program_name}"

    @property
    def is_on(self) -> bool:
        """Return True if this program letter is in device['active_programs']."""
        raw     = self._device.get("active_programs", "")
        letters = set(raw.strip("[]").split(","))
        return self._program in letters

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return meteo pause weather data for this program."""
        try:
            programs = json.loads(self._device.get("meteo_pause_json", "[]"))
            for p in programs:
                if p.get("name") == self._program:
                    return {
                        "should_run": p.get("should_run", True),
                        "pop":        p.get("pop"),
                        "rain":       p.get("rain"),
                        "temp":       p.get("temp"),
                    }
        except (json.JSONDecodeError, TypeError):
            pass
        return {}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable this program."""
        await self.coordinator.api.set_program_active(
            self._cloud_id, self._device_id, self._program, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable this program."""
        await self.coordinator.api.set_program_active(
            self._cloud_id, self._device_id, self._program, False
        )
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self._device, self._cloud)
