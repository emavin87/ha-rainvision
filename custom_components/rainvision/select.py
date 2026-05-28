"""
Rain Vision Select Entities
============================
Exposes dropdown selects that list all discovered Nuvola hubs and
Pure Vision devices. These entities serve as a convenient reference
panel: selecting an entry shows its cloud_id, device_id and puid
in the extra attributes — the values needed for service calls.

Select types:
  RainVisionCloudSelect  — all Nuvola hubs (shows cloud_id in attributes)
  RainVisionDeviceSelect — all Pure Vision devices (shows device_id + puid)
  RainVisionPuidSelect   — all device PUIDs (shows puid + device_id)
"""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RainVisionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rain Vision select helper entities.

    Creates one set of three select entities per config entry.
    These are global helpers not tied to a specific device.

    Args:
        hass:               Home Assistant instance.
        entry:              Config entry being set up.
        async_add_entities: Callback to register entities with HA.
    """
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RainVisionCloudSelect(coordinator,  entry.entry_id),
        RainVisionDeviceSelect(coordinator, entry.entry_id),
        RainVisionPuidSelect(coordinator,   entry.entry_id),
    ])


class RainVisionCloudSelect(CoordinatorEntity, SelectEntity):
    """Dropdown listing all discovered Nuvola Vision hubs.

    The selected option's cloud_id is exposed in extra_state_attributes
    so it can be copied into manual_start / manual_stop service calls.

    Options format: 'ID: <cloud_id> — <name>'
    """

    _attr_icon = "mdi:cloud"

    def __init__(self, coordinator: RainVisionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id       = entry_id
        self._attr_unique_id = f"{entry_id}_cloud_select"
        self._current: str | None = None

    @property
    def name(self) -> str:
        return "Rain Vision — Select Nuvola Hub"

    @property
    def options(self) -> list[str]:
        return [
            f"ID: {cid} — {cloud.get('name', f'Nuvola {cid}')}"
            for cid, cloud in self.coordinator.clouds.items()
        ]

    @property
    def current_option(self) -> str | None:
        opts = self.options
        if not opts:
            return None
        if self._current not in opts:
            self._current = opts[0]
        return self._current

    async def async_select_option(self, option: str) -> None:
        self._current = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose cloud_id, name, online and battery for the selected hub."""
        for cid, cloud in self.coordinator.clouds.items():
            if f"ID: {cid} — {cloud.get('name', f'Nuvola {cid}')}" == self._current:
                return {
                    "cloud_id": cid,
                    "name":     cloud.get("name"),
                    "online":   cloud.get("online"),
                    "battery":  cloud.get("battery"),
                }
        return {}


class RainVisionDeviceSelect(CoordinatorEntity, SelectEntity):
    """Dropdown listing all discovered Pure Vision irrigation controllers.

    The selected option's device_id and cloud_id are exposed in
    extra_state_attributes for use in service calls.

    Options format: 'ID: <device_id> — <name>'
    """

    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator: RainVisionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id       = entry_id
        self._attr_unique_id = f"{entry_id}_device_select"
        self._current: str | None = None

    @property
    def name(self) -> str:
        return "Rain Vision — Select Device"

    @property
    def options(self) -> list[str]:
        return [
            f"ID: {did} — {dev.get('name', f'Device {did}')}"
            for did, dev in self.coordinator.devices.items()
        ]

    @property
    def current_option(self) -> str | None:
        opts = self.options
        if not opts:
            return None
        if self._current not in opts:
            self._current = opts[0]
        return self._current

    async def async_select_option(self, option: str) -> None:
        self._current = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose device_id, puid, cloud_id, name, online and battery for the selected device."""
        for did, dev in self.coordinator.devices.items():
            if f"ID: {did} — {dev.get('name', f'Device {did}')}" == self._current:
                return {
                    "device_id": did,
                    "puid":      dev.get("puid"),
                    "cloud_id":  dev.get("_cloud_id"),
                    "name":      dev.get("name"),
                    "online":    dev.get("online"),
                    "battery":   dev.get("battery"),
                }
        return {}


class RainVisionPuidSelect(CoordinatorEntity, SelectEntity):
    """Dropdown listing all device PUIDs.

    The PUID is needed for program management services
    (set_zone_duration, set_program_start_time, set_program_cycle,
    set_program_weekdays, set_programs).

    Options format: 'PUID: <puid> — <name>'
    """

    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator: RainVisionCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id       = entry_id
        self._attr_unique_id = f"{entry_id}_puid_select"
        self._current: str | None = None

    @property
    def name(self) -> str:
        return "Rain Vision — Select Device PUID"

    @property
    def options(self) -> list[str]:
        return [
            f"PUID: {dev.get('puid', did)} — {dev.get('name', f'Device {did}')}"
            for did, dev in self.coordinator.devices.items()
            if dev.get("puid")
        ]

    @property
    def current_option(self) -> str | None:
        opts = self.options
        if not opts:
            return None
        if self._current not in opts:
            self._current = opts[0]
        return self._current

    async def async_select_option(self, option: str) -> None:
        self._current = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose puid, device_id, cloud_id and name for the selected entry."""
        for did, dev in self.coordinator.devices.items():
            if f"PUID: {dev.get('puid', did)} — {dev.get('name', f'Device {did}')}" == self._current:
                return {
                    "puid":      dev.get("puid"),
                    "device_id": did,
                    "cloud_id":  dev.get("_cloud_id"),
                    "name":      dev.get("name"),
                }
        return {}
