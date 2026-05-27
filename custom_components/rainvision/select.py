"""
Rain Vision Select Entities
=============================
This module exposes dropdown select entities that list the available
clouds (Nuvola hubs) and devices (Pure Vision controllers) discovered
by the coordinator.

These entities serve two purposes:
1. Let the user visually browse which clouds/devices are configured.
2. Provide a convenient way to pick cloud_id, device_id and device_puid
   values needed by the Rain Vision services (manual_start, manual_stop,
   set_zone_duration, etc.) directly from the HA UI.

Select types:
    - RainVisionCloudSelect  : Dropdown of all Nuvola hubs (cloud_id → name)
    - RainVisionDeviceSelect : Dropdown of all Pure Vision devices (device_id → name)
    - RainVisionPuidSelect   : Dropdown of all device PUIDs (puid → name)

The selected value is the ID/PUID string so it can be copy-pasted directly
into service calls. The state updates automatically on every coordinator poll.
"""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up Rain Vision select entities.

    Creates one RainVisionCloudSelect per place (listing all Nuvola hubs),
    one RainVisionDeviceSelect per place (listing all Pure Vision devices),
    and one RainVisionPuidSelect per place (listing all device PUIDs).

    These are global helper entities not tied to a specific device.
    """
    coordinator: RainVisionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    # One set of selects per config entry (global helpers)
    entities.append(RainVisionCloudSelect(coordinator, entry.entry_id))
    entities.append(RainVisionDeviceSelect(coordinator, entry.entry_id))
    entities.append(RainVisionPuidSelect(coordinator, entry.entry_id))

    async_add_entities(entities)


class RainVisionCloudSelect(CoordinatorEntity, SelectEntity):
    """Dropdown select listing all discovered Nuvola cloud hubs.

    The state is the cloud_id (as string) of the currently selected hub.
    The options list is built dynamically from coordinator.clouds on
    every coordinator update.

    Use this entity to find the cloud_id value needed for
    manual_start and manual_stop service calls.

    State: cloud_id string of the selected hub (e.g. '1099').
    Options: 'ID: <id> — <name>' for each discovered hub.
    """

    _attr_icon = "mdi:cloud"

    def __init__(self, coordinator: RainVisionCoordinator, entry_id: str) -> None:
        """Initialize the cloud select entity.

        Args:
            coordinator: The shared data coordinator.
            entry_id: Config entry id, used to build the unique_id.
        """
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_cloud_select"
        # Start with the first available cloud selected
        self._current: str | None = None

    @property
    def name(self) -> str:
        return "Rain Vision — Seleziona Hub Nuvola"

    @property
    def options(self) -> list[str]:
        """Return one option per discovered Nuvola hub.

        Format: 'ID: <cloud_id> — <cloud_name>'
        """
        return [
            f"ID: {cid} — {cloud.get('name', f'Nuvola {cid}')}"
            for cid, cloud in self.coordinator.clouds.items()
        ]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option, defaulting to the first."""
        opts = self.options
        if not opts:
            return None
        # Keep current selection if still valid, otherwise default to first
        if self._current in opts:
            return self._current
        self._current = opts[0]
        return self._current

    async def async_select_option(self, option: str) -> None:
        """Handle the user selecting a different hub."""
        self._current = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose raw cloud_id and name for the selected hub."""
        for cid, cloud in self.coordinator.clouds.items():
            label = f"ID: {cid} — {cloud.get('name', f'Nuvola {cid}')}"
            if label == self._current:
                return {
                    "cloud_id": cid,
                    "name": cloud.get("name"),
                    "online": cloud.get("online"),
                    "battery": cloud.get("battery"),
                }
        return {}


class RainVisionDeviceSelect(CoordinatorEntity, SelectEntity):
    """Dropdown select listing all discovered Pure Vision devices.

    The state is the device_id (as string) of the currently selected device.
    Use this entity to find the device_id value needed for
    manual_start and manual_stop service calls.

    State: device_id string of the selected device (e.g. '5644').
    Options: 'ID: <device_id> — <device_name>' for each discovered device.
    """

    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator: RainVisionCoordinator, entry_id: str) -> None:
        """Initialize the device select entity.

        Args:
            coordinator: The shared data coordinator.
            entry_id: Config entry id, used to build the unique_id.
        """
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_device_select"
        self._current: str | None = None

    @property
    def name(self) -> str:
        return "Rain Vision — Seleziona Dispositivo"

    @property
    def options(self) -> list[str]:
        """Return one option per discovered Pure Vision device.

        Format: 'ID: <device_id> — <device_name>'
        """
        return [
            f"ID: {did} — {dev.get('name', f'Device {did}')}"
            for did, dev in self.coordinator.devices.items()
        ]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option, defaulting to the first."""
        opts = self.options
        if not opts:
            return None
        if self._current in opts:
            return self._current
        self._current = opts[0]
        return self._current

    async def async_select_option(self, option: str) -> None:
        """Handle the user selecting a different device."""
        self._current = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose raw device_id, puid, cloud_id and name for the selected device."""
        for did, dev in self.coordinator.devices.items():
            label = f"ID: {did} — {dev.get('name', f'Device {did}')}"
            if label == self._current:
                return {
                    "device_id": did,
                    "puid": dev.get("puid"),
                    "cloud_id": dev.get("_cloud_id"),
                    "name": dev.get("name"),
                    "online": dev.get("online"),
                    "battery": dev.get("battery"),
                }
        return {}


class RainVisionPuidSelect(CoordinatorEntity, SelectEntity):
    """Dropdown select listing all device PUIDs.

    The PUID is needed for program management service calls
    (set_zone_duration, set_program_start_time, set_program_cycle,
    set_program_weekdays, set_programs).

    State: PUID string of the selected device (e.g. '1000005059').
    Options: 'PUID: <puid> — <device_name>' for each discovered device.
    """

    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator: RainVisionCoordinator, entry_id: str) -> None:
        """Initialize the PUID select entity.

        Args:
            coordinator: The shared data coordinator.
            entry_id: Config entry id, used to build the unique_id.
        """
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_puid_select"
        self._current: str | None = None

    @property
    def name(self) -> str:
        return "Rain Vision — Seleziona PUID Dispositivo"

    @property
    def options(self) -> list[str]:
        """Return one option per device, using PUID as the identifier.

        Format: 'PUID: <puid> — <device_name>'
        """
        return [
            f"PUID: {dev.get('puid', did)} — {dev.get('name', f'Device {did}')}"
            for did, dev in self.coordinator.devices.items()
            if dev.get("puid")
        ]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option, defaulting to the first."""
        opts = self.options
        if not opts:
            return None
        if self._current in opts:
            return self._current
        self._current = opts[0]
        return self._current

    async def async_select_option(self, option: str) -> None:
        """Handle the user selecting a different PUID."""
        self._current = option
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Expose raw puid, device_id and name for the selected device."""
        for did, dev in self.coordinator.devices.items():
            label = f"PUID: {dev.get('puid', did)} — {dev.get('name', f'Device {did}')}"
            if label == self._current:
                return {
                    "puid": dev.get("puid"),
                    "device_id": did,
                    "cloud_id": dev.get("_cloud_id"),
                    "name": dev.get("name"),
                }
        return {}
