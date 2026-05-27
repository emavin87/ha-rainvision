"""DataUpdateCoordinator for Rain Vision."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RainVisionApi, RainVisionApiError, RainVisionAuthError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class RainVisionCoordinator(DataUpdateCoordinator):
    """Coordinator that polls Rain Vision API and shares data with all entities."""

    def __init__(self, hass: HomeAssistant, api: RainVisionApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api = api
        self.places: list[dict] = []
        self.clouds: dict[int, dict] = {}    # cloud_id -> cloud data
        self.devices: dict[int, dict] = {}   # device_id -> device data
        self.programs: dict[int, list] = {}  # device_id -> list of programs

    async def _async_update_data(self) -> dict:
        """Fetch data from Rain Vision API."""
        try:
            places = await self.api.get_places()
        except RainVisionAuthError as err:
            raise UpdateFailed(f"Autenticazione fallita: {err}") from err
        except RainVisionApiError as err:
            raise UpdateFailed(f"Errore API: {err}") from err

        self.places = places
        self.clouds = {}
        self.devices = {}

        for place in places:
            for cloud in place.get("clouds", []):
                cloud_id = cloud["id"]
                self.clouds[cloud_id] = cloud
                for device in cloud.get("devices", []):
                    device_id = device["id"]
                    device["_cloud_id"] = cloud_id
                    self.devices[device_id] = device

                    # Fetch full program list for each device
                    puid = device.get("puid")
                    if puid:
                        try:
                            programs = await self.api.get_device_program_list(puid)
                            self.programs[device_id] = programs
                        except (RainVisionApiError, RainVisionAuthError) as err:
                            _LOGGER.warning(
                                "Impossibile caricare programmi per device %s: %s",
                                device_id, err,
                            )
                            self.programs.setdefault(device_id, [])

        return {
            "places": places,
            "clouds": self.clouds,
            "devices": self.devices,
            "programs": self.programs,
        }
