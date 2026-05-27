"""DataUpdateCoordinator for the Rainvision integration.

Fetches all required API data in a single update cycle and exposes it to
platform entities through coordinator.data.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RainvisionApiClient, RainvisionAuthError, RainvisionConnectionError
from .const import (
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    COORDINATOR_DEVICE,
    COORDINATOR_STAT,
    COORDINATOR_PROGRAMS,
    COORDINATOR_ZONES,
)

_LOGGER = logging.getLogger(__name__)


class RainvisionCoordinator(DataUpdateCoordinator):
    """Aggregates data from all Rainvision API endpoints into a single dict.

    coordinator.data structure:
        {
            COORDINATOR_DEVICE:   response from GET nuvola/device
            COORDINATOR_STAT:     response from GET nuvola/stat
            COORDINATOR_PROGRAMS: response from GET GetProgramNames
            COORDINATOR_ZONES:    response from GET GetZoneNames
        }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: RainvisionApiClient,
        cloud_puid: str,
        device_puid: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        # PUIDs are stored so platform modules can reference them for DeviceInfo
        self.cloud_puid = cloud_puid
        self.device_puid = device_puid

    async def _async_update_data(self) -> dict:
        """Fetch fresh data from every required API endpoint.

        Raises:
            UpdateFailed: Wraps auth and connection errors so HA can surface
                          them cleanly in the UI without crashing the coordinator.
        """
        try:
            device = await self.client.get_device_status(self.device_puid)
            stat = await self.client.get_nuvola_stat(self.cloud_puid)
            programs = await self.client.get_program_names(self.device_puid)
            zones = await self.client.get_zone_names(self.device_puid)
        except RainvisionAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RainvisionConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        return {
            COORDINATOR_DEVICE: device,
            COORDINATOR_STAT: stat,
            COORDINATOR_PROGRAMS: programs,
            COORDINATOR_ZONES: zones,
        }
