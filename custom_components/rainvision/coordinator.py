"""
Rain Vision Data Coordinator
=============================
This module defines the DataUpdateCoordinator that acts as the single
source of truth for all Rain Vision data within Home Assistant.

The coordinator is responsible for:
- Polling the Rain Vision API at a configurable interval (default: 60s)
- Fetching places, clouds (Nuvola hubs), devices (Pure Vision controllers)
  and their full program lists
- Storing all fetched data in structured dicts keyed by id, so that
  individual sensor/switch entities can access their slice of data
  without making independent API calls

All entities (sensors and switches) extend CoordinatorEntity and receive
automatic state updates whenever the coordinator completes a poll cycle.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RainVisionApi, RainVisionApiError, RainVisionAuthError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class RainVisionCoordinator(DataUpdateCoordinator):
    """Central data coordinator for the Rain Vision integration.

    Polls the Rain Vision cloud API at a regular interval and caches
    the results in structured dictionaries. All HA entities read their
    state from these dictionaries rather than querying the API directly.

    Attributes:
        api (RainVisionApi): The authenticated API client instance.
        places (list[dict]): Raw list of place objects from GetPlaces.
        clouds (dict[int, dict]): Map of cloud_id → cloud data dict.
            Each cloud represents a Nuvola Vision hub device.
        devices (dict[int, dict]): Map of device_id → device data dict.
            Each device represents a Pure Vision irrigation controller.
            Includes a '_cloud_id' key injected by the coordinator for
            easy parent-cloud lookup.
        programs (dict[int, list]): Map of device_id → list of program dicts
            as returned by GetDeviceProgramList. Each program includes
            times, zones with durations, weekdays, and cycle frequency.
    """

    def __init__(self, hass: HomeAssistant, api: RainVisionApi) -> None:
        """Initialize the coordinator.

        Args:
            hass: The Home Assistant instance.
            api: An authenticated RainVisionApi client.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api = api
        self.places: list[dict] = []
        self.clouds: dict[int, dict] = {}
        self.devices: dict[int, dict] = {}
        self.programs: dict[int, list] = {}

    async def _async_update_data(self) -> dict:
        """Fetch and cache all Rain Vision data from the API.

        Called automatically by the DataUpdateCoordinator base class at
        every poll interval (and immediately on first setup via
        async_config_entry_first_refresh).

        The method:
        1. Calls GetPlaces to retrieve all places with their clouds and devices.
        2. Builds the self.clouds and self.devices lookup dicts.
        3. For each device, calls GetDeviceProgramList to fetch full program data.
           If the program fetch fails for a device, a warning is logged and
           an empty list is stored — the coordinator does not abort entirely.

        Returns:
            A dict with keys 'places', 'clouds', 'devices', 'programs',
            mirroring the instance attributes. Returned to satisfy the
            DataUpdateCoordinator contract (stored as self.data).

        Raises:
            UpdateFailed: If the main GetPlaces call fails for any reason
                          (auth error or network error). This causes HA to
                          mark the integration as unavailable.
        """
        try:
            places = await self.api.get_places()
        except RainVisionAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RainVisionApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        self.places = places
        self.clouds = {}
        self.devices = {}

        for place in places:
            for cloud in place.get("clouds", []):
                cloud_id = cloud["id"]
                self.clouds[cloud_id] = cloud

                for device in cloud.get("devices", []):
                    device_id = device["id"]
                    # Inject parent cloud_id so entities can navigate up easily
                    device["_cloud_id"] = cloud_id
                    self.devices[device_id] = device

                    # Fetch detailed program list for each device.
                    # Failures here are non-fatal: we log a warning and
                    # keep any previously cached programs for the device.
                    puid = device.get("puid")
                    if puid:
                        try:
                            programs = await self.api.get_device_program_list(puid)
                            self.programs[device_id] = programs
                        except (RainVisionApiError, RainVisionAuthError) as err:
                            _LOGGER.warning(
                                "Could not fetch programs for device %s: %s",
                                device_id, err,
                            )
                            self.programs.setdefault(device_id, [])

        return {
            "places": places,
            "clouds": self.clouds,
            "devices": self.devices,
            "programs": self.programs,
        }
