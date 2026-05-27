"""Switch entities for Rain Vision zones and programs."""
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
    """Set up Rain Vision switches."""
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []

    for cloud_id, cloud in coordinator.clouds.items():
        for device in cloud.get("devices", []):
            device_id = device["id"]

            # One switch per zone
            zone_names = {
                z["zone_progressive"]: z.get("custom_name") or z.get("default_name", f"Zone {z['zone_progressive']}")
                for z in device.get("zonenames", [])
            }
            num_zones = device.get("devicetype", {}).get("zones", 0)
            for zone_num in range(1, num_zones + 1):
                zone_name = zone_names.get(zone_num, f"Zone {zone_num}")
                entities.append(
                    RainVisionZoneSwitch(coordinator, cloud_id, device_id, zone_num, zone_name)
                )

            # One switch per program
            for prog in device.get("fullprogramnames", []):
                letter = prog.get("program_progressive", "")
                custom = prog.get("custom_name") or prog.get("default_name", f"Programma {letter}")
                entities.append(
                    RainVisionProgramSwitch(coordinator, cloud_id, device_id, letter, custom)
                )

    async_add_entities(entities)


def _device_device_info(device: dict, cloud: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"device_{device['id']}")},
        name=device.get("name", f"Device {device['id']}"),
        manufacturer=MANUFACTURER,
        model=device.get("devicetype", {}).get("name", MODEL_DEVICE),
        sw_version=device.get("firmware", {}).get("name"),
        via_device=(DOMAIN, f"cloud_{cloud['id']}"),
    )


class RainVisionZoneSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to manually start/stop a single irrigation zone."""

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
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._zone = zone
        self._zone_name = zone_name
        self._attr_unique_id = f"device_{device_id}_zone_{zone}"
        # Optimistic state while waiting for next poll
        self._is_on: bool = False

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        device_name = self._device.get("name", "Device")
        return f"{device_name} {self._zone_name}"

    @property
    def is_on(self) -> bool:
        """
        Determine if zone is active from the 'manual' hex string.
        Byte at position (zone-1)*2 encodes zone activity.
        Falls back to optimistic state.
        """
        manual_hex = self._device.get("manual", "")
        if manual_hex:
            try:
                # Each zone uses 2 hex chars (1 byte), zone 1 starts at index 2
                # First byte (index 0-1) is a command byte
                offset = self._zone * 2  # zone 1 -> offset 2, zone 2 -> offset 4, ...
                if len(manual_hex) >= offset + 2:
                    byte_val = int(manual_hex[offset: offset + 2], 16)
                    return byte_val > 0
            except ValueError:
                pass
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "zone_number": self._zone,
            "cloud_id": self._cloud_id,
            "device_id": self._device_id,
            "default_duration_minutes": DEFAULT_MANUAL_DURATION,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start manual irrigation on this zone."""
        duration = kwargs.get("duration", DEFAULT_MANUAL_DURATION)
        success = await self.coordinator.api.manual_start_zone(
            self._cloud_id, self._device_id, self._zone, duration
        )
        if success:
            self._is_on = True
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop manual irrigation."""
        success = await self.coordinator.api.manual_stop(self._cloud_id, self._device_id)
        if success:
            self._is_on = False
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        return _device_device_info(self._device, self._cloud)


class RainVisionProgramSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable an irrigation program (A/B/C/D)."""

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
        super().__init__(coordinator)
        self._cloud_id = cloud_id
        self._device_id = device_id
        self._program = program
        self._program_name = program_name
        self._attr_unique_id = f"device_{device_id}_program_{program}"

    @property
    def _device(self) -> dict:
        return self.coordinator.devices.get(self._device_id, {})

    @property
    def _cloud(self) -> dict:
        return self.coordinator.clouds.get(self._cloud_id, {})

    @property
    def name(self) -> str:
        device_name = self._device.get("name", "Device")
        return f"{device_name} Programma {self._program} - {self._program_name}"

    @property
    def is_on(self) -> bool:
        """Program is on if it appears in active_programs."""
        active_raw = self._device.get("active_programs", "")
        active_letters = set(active_raw.strip("[]").split(","))
        return self._program in active_letters

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show meteo pause info for this program."""
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
        return _device_device_info(self._device, self._cloud)
