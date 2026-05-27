"""Async HTTP client for the Rainvision v5 cloud API."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)


class RainvisionAuthError(Exception):
    """Raised when the API returns a 401 or the token is missing."""


class RainvisionConnectionError(Exception):
    """Raised on network failures or unexpected HTTP status codes."""


class RainvisionApiClient:
    """Wraps every Rainvision v5 endpoint used by this integration.

    All methods are coroutines and must be awaited.
    Authentication is Bearer-token based: call authenticate() once to obtain
    a token, which is then stored and sent automatically on every subsequent
    request.
    """

    def __init__(self, session: aiohttp.ClientSession, token: str | None = None) -> None:
        self._session = session
        self._token = token

    @property
    def token(self) -> str | None:
        """Return the current Bearer token, or None if not authenticated."""
        return self._token

    async def _request(self, endpoint: str, body: dict | None = None) -> dict[str, Any]:
        """Send an authenticated POST request and return the parsed JSON body.

        Args:
            endpoint: API path relative to BASE_URL (e.g. "nuvola/device").
            body: Optional JSON payload; defaults to an empty dict.

        Raises:
            RainvisionAuthError: HTTP 401 received.
            RainvisionConnectionError: Any other non-200 status or network error.
        """
        url = f"{BASE_URL}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with self._session.post(url, json=body or {}, headers=headers) as resp:
                if resp.status == 401:
                    raise RainvisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainvisionConnectionError(
                        f"HTTP {resp.status} from endpoint '{endpoint}'"
                    )
                return await resp.json()
        except aiohttp.ClientError as err:
            raise RainvisionConnectionError(f"Network error: {err}") from err

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> str:
        """Log in with email/password and store the returned Bearer token.

        Calls POST /token with device_name = "homeassistant".

        Args:
            email: Rainvision account email address.
            password: Rainvision account password.

        Returns:
            The Bearer token string.

        Raises:
            RainvisionAuthError: If the response does not contain a token.
        """
        data = await self._request("token", {
            "email": email,
            "password": password,
            "device_name": "homeassistant",
        })
        token = data.get("token")
        if not token:
            raise RainvisionAuthError("No token in authentication response")
        self._token = token
        return token

    async def check_token(self) -> bool:
        """Verify that the current Bearer token is still valid.

        Calls POST /check-token (no body required). The endpoint returns HTTP
        200 with a success payload when the token is valid, or HTTP 401 when
        it has expired or been revoked.

        Returns:
            True if the token is valid, False otherwise.

        Note:
            This method intentionally catches RainvisionAuthError and returns
            False rather than raising, so callers can branch on the result
            without needing a try/except block.
        """
        try:
            await self._request("check-token")
            return True
        except RainvisionAuthError:
            return False

    # -------------------------------------------------------------------------
    # Places
    # -------------------------------------------------------------------------

    async def get_places(self) -> dict[str, Any]:
        """Return all places (sites) associated with the account.

        Calls POST /GetPlaces — no body required.
        Response key: places / self_places.
        """
        return await self._request("GetPlaces")

    async def get_place_details(self, place_id: int) -> dict[str, Any]:
        """Return full details for a single place, including current weather.

        Calls POST /GetPlaceDetails with {"place_id": <int>}.
        Response key: place (contains meteo, alarms, lat/lng, …).
        """
        return await self._request("GetPlaceDetails", {"place_id": place_id})

    # -------------------------------------------------------------------------
    # Hub (Nuvola)
    # -------------------------------------------------------------------------

    async def get_nuvola_stat(self, cloud_puid: str, utc_offset: int = 120) -> dict[str, Any]:
        """Return status and metadata for the NUVOLA VISION hub.

        Calls POST /nuvola/stat.

        Args:
            cloud_puid: PUID of the Nuvola hub (e.g. "2000001121").
            utc_offset: UTC offset in minutes for the device's timezone.

        Response keys: cloud (battery, firmware, lat/lng, …), devstat.
        """
        return await self._request("nuvola/stat", {
            "cloud_puid": cloud_puid,
            "utcOffsetMinutes": utc_offset,
            "forceRefresh": False,
        })

    async def scan_ble_peers(
        self, cloud_puid: str, utc_offset: int = 120
    ) -> dict[str, Any]:
        """Trigger a full BLE scan from the Nuvola hub and return found peers.

        Calls POST /nuvola/scan/full.
        Peers include battery-powered sensors such as ACQUA VISION.

        Args:
            cloud_puid: PUID of the Nuvola hub.
            utc_offset: UTC offset in minutes.

        Response key: peers (list of BLE devices with puid, battery, devicetype, …).
        """
        return await self._request("nuvola/scan/full", {
            "cloud_puid": cloud_puid,
            "scan_type": 1,
            "forceRefresh": False,
            "utcOffsetInMinutes": utc_offset,
        })

    # -------------------------------------------------------------------------
    # Irrigation device (PURE VISION)
    # -------------------------------------------------------------------------

    async def get_device_status(
        self, device_puid: str, utc_offset: int = 120, force: bool = False
    ) -> dict[str, Any]:
        """Return the live status of an irrigation controller.

        Calls POST /nuvola/device.
        The response contains raw hex status strings (status, settings, pause,
        extravalve) plus battery level and the full device record.

        Args:
            device_puid: PUID of the irrigation device (e.g. "1000005059").
            utc_offset: UTC offset in minutes.
            force: When True the hub fetches fresh data instead of using cache.
        """
        return await self._request("nuvola/device", {
            "device_puid": device_puid,
            "utcOffsetInMinutes": utc_offset,
            "forceRefresh": force,
        })

    async def get_program_names(self, device_puid: str) -> dict[str, Any]:
        """Return program names and weather-based pause data for a device.

        Calls POST /GetProgramNames.
        The response embeds meteo_pause_json: a JSON string with per-program
        weather variables (temp, wind, pop, should_run, irrigation_variable, …).

        Args:
            device_puid: PUID of the irrigation device.
        """
        return await self._request("GetProgramNames", {"device_puid": device_puid})

    async def get_zone_names(self, device_puid: str) -> dict[str, Any]:
        """Return zone names (both default and user-defined) for a device.

        Calls POST /GetZoneNames.
        Response includes fullzonenames: list of {zone_progressive, default_name,
        custom_name}.

        Args:
            device_puid: PUID of the irrigation device.
        """
        return await self._request("GetZoneNames", {"device_puid": device_puid})

    async def get_program_list(self, device_puid: str, offset: str = "GMT+0200") -> dict[str, Any]:
        """Return the full schedule for every program on a device.

        Calls POST /GetDeviceProgramList.
        Each program entry contains times (up to 6 start times), zones with
        durations, cycle interval, weekday flags, and schedule type.

        Args:
            device_puid: PUID of the irrigation device.
            offset: Timezone offset string used by the API (e.g. "GMT+0200").
        """
        return await self._request("GetDeviceProgramList", {
            "id": device_puid,
            "offset": offset,
        })

    async def get_mode(self, puid: str) -> dict[str, Any]:
        """Return the current operating mode of a device.

        Calls POST /GetMode.
        Response: {"mode": <int>}  — 0 = automatic, 1 = manual.

        Args:
            puid: PUID of the device.
        """
        return await self._request("GetMode", {"puid": puid})
