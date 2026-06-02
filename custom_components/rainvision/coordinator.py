"""
Rain Vision Data Coordinator
=============================
Central DataUpdateCoordinator that polls the Rain Vision cloud API and
caches the results so all HA entities share a single HTTP request cycle.

Poll sequence on each update:
  1. GetPlaces            — builds self.clouds and self.devices dicts
  2. nuvola/device        — real-time status (battery, status hex) per device
  3. GetDeviceProgramList — full program/zone data per device

All entities extend CoordinatorEntity and are updated automatically
whenever _async_update_data() completes successfully.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RainVisionApi, RainVisionApiError, RainVisionAuthError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class RainVisionCoordinator(DataUpdateCoordinator):
    """Coordinator that owns all Rain Vision data for a single config entry.

    Attributes:
        api      (RainVisionApi):       Authenticated API client.
        places   (list[dict]):          Raw place objects from GetPlaces.
        clouds   (dict[int, dict]):     cloud_id → cloud data dict (Nuvola hubs).
        devices  (dict[int, dict]):     device_id → device data dict (Pure Vision).
                                        Each device has '_cloud_id' injected for
                                        easy parent-cloud navigation.
        programs (dict[int, list]):     device_id → program list from GetDeviceProgramList.
        realtime (dict[int, dict]):     device_id → real-time status from nuvola/device.
    """

    def __init__(self, hass: HomeAssistant, api: RainVisionApi) -> None:
        """Initialise the coordinator.

        Args:
            hass: Home Assistant instance.
            api:  Authenticated RainVisionApi client.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api      = api
        self.places:   list[dict]       = []
        self.clouds:   dict[int, dict]  = {}
        self.devices:  dict[int, dict]  = {}
        self.programs: dict[int, list]  = {}
        self.realtime: dict[int, dict]  = {}
        self.scan_peers:  dict[int, dict] = {}   # device_id -> peer dict from nuvola/scan/full
        self.last_poll_at: str | None       = None  # ISO timestamp of last successful poll
                                                   # covers ALL BLE devices (Pure Vision, Acqua Vision, etc.)

    async def _async_update_data(self) -> dict:
        """Fetch all Rain Vision data from the API.

        Called by HA at every UPDATE_INTERVAL and immediately on first setup.

        Steps:
          1. GetPlaces — main structural data (clouds, devices, zones, programs).
          2. nuvola/device — real-time status per device (battery, status hex).
             Failures are non-fatal: a warning is logged and the previous
             cached value is kept.
          3. GetDeviceProgramList — detailed program/zone data per device.
             Also non-fatal per device.

        Returns:
            Dict mirroring the coordinator attributes (used as self.data).

        Raises:
            UpdateFailed: If GetPlaces fails. HA marks the integration
                          as unavailable until the next successful poll.
        """
        # ── Step 1: GetPlaces ─────────────────────────────────────────────────
        try:
            places = await self.api.get_places()
        except RainVisionAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RainVisionApiError as err:
            raise UpdateFailed(f"API error on GetPlaces: {err}") from err

        self.places  = places
        self.clouds  = {}
        self.devices = {}

        for place in places:
            for cloud in place.get("clouds", []):
                cloud_id = cloud["id"]
                self.clouds[cloud_id] = cloud
                for device in cloud.get("devices", []):
                    device_id = device["id"]
                    device["_cloud_id"] = cloud_id   # inject parent reference
                    self.devices[device_id] = device

        # ── Step 2: nuvola/device (real-time status) ──────────────────────────
        for device_id, device in self.devices.items():
            puid = device.get("puid")
            if not puid:
                continue
            try:
                rt = await self.api.get_device_realtime(puid)
                # Response structure:
                # {
                #   timestamp: "2026-05-30T19:00:51.185141Z",  <- last update
                #   next_update: null,
                #   data: {
                #     status: {
                #       battery: 83,
                #       status:  "000100...",  <- zone state hex
                #       pause:   "3804...",    <- pause hex
                #       settings: "...",
                #       timestamp: { MSG_ID, RESULT, ARGS }
                #     }
                #   },
                #   device: { ...full device object... },
                #   device.cloud: { ...Nuvola object with meteo... }
                # }
                self.realtime[device_id] = rt
            except (RainVisionApiError, RainVisionAuthError) as err:
                _LOGGER.warning(
                    "Could not fetch real-time status for device %s: %s", device_id, err
                )
                self.realtime.setdefault(device_id, {})

        # ── Step 2b: nuvola/scan/full (RSSI + BLE peers) ─────────────────────
        for cloud_id, cloud in self.clouds.items():
            cloud_puid = cloud.get("puid")
            if not cloud_puid:
                continue
            try:
                import datetime as _dt
                tz_offset = int(_dt.datetime.now().astimezone().utcoffset().total_seconds() / 60)
                peers = await self.api.get_nuvola_scan(cloud_puid, utc_offset_minutes=tz_offset)
                for peer in peers:
                    dev_obj = peer.get("device") or {}
                    dev_id  = dev_obj.get("id")
                    if not dev_id:
                        continue
                    self.scan_peers[dev_id] = {
                        "rssi":       peer.get("rssi"),
                        "battery":    peer.get("battery"),
                        "fw":         peer.get("fw"),
                        "paired":     peer.get("paired"),
                        "mdata":      peer.get("mdata"),
                        "cloud_id":   cloud_id,
                        "device":     dev_obj,
                        "devicetype": peer.get("devicetype") or {},
                    }
            except (RainVisionApiError, RainVisionAuthError) as err:
                _LOGGER.warning("Could not fetch BLE scan for cloud %s: %s", cloud_id, err)

        # ── Step 3: GetDeviceProgramList ──────────────────────────────────────
        for device_id, device in self.devices.items():
            puid = device.get("puid")
            if not puid:
                continue
            try:
                programs = await self.api.get_device_program_list(puid)

                # Build a lookup: zone_progressive -> display name.
                # Zone names live in device["zonenames"] from GetPlaces,
                # not inside GetDeviceProgramList, so we inject them here.
                zone_names = {
                    z["zone_progressive"]: (
                        z.get("custom_name") or z.get("default_name", f"Zone {z['zone_progressive']}")
                    )
                    for z in device.get("zonenames", [])
                }

                # Inject zone display names from GetPlaces into each program zone
                for prog in programs:
                    for zone in prog.get("zones", []):
                        progressive = zone.get("progressive")
                        zone["name"] = zone_names.get(progressive, f"Zone {progressive}")

                # Filter out programs E-H (not yet supported)
                # They may contain JS date strings in times and are unused
                programs = [p for p in programs if p.get("name") in ("A", "B", "C", "D")]

                self.programs[device_id] = programs
            except (RainVisionApiError, RainVisionAuthError) as err:
                _LOGGER.warning(
                    "Could not fetch programs for device %s: %s", device_id, err
                )
                self.programs.setdefault(device_id, [])

        return {
            "places":   self.places,
            "clouds":   self.clouds,
            "devices":  self.devices,
            "programs": self.programs,
            "realtime": self.realtime,
        }
