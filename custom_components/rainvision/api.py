"""
Rain Vision API Client
======================
Async HTTP client for the Rain Vision REST API (https://www.rainvision.it/api/v5).

Discovered endpoints (from HAR capture):
  POST /token                   — login, returns api_token
  POST /check-token             — validate an existing token
  POST /GetPlacesList           — lightweight list of places
  POST /GetPlaces               — full places with clouds and devices
  POST /nuvola/device           — real-time device status (battery, status hex, pauses)
  POST /GetDeviceProgramList    — full program list with zones and durations
  POST /GetZoneNames            — zone names for a device
  POST /GetProgramNames         — program names for a device
  POST /SetDeviceProgramsNuvola — save full programs payload

All methods are async and use an injected aiohttp.ClientSession.
Auth errors raise RainVisionAuthError; all other failures raise RainVisionApiError.
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.rainvision.it/api/v5"

# Default headers required by every Rain Vision API request
HEADERS_BASE: dict[str, str] = {
    "Content-Type":   "application/json",
    "Content-Language": "it",
    "Accept":         "application/json, text/plain, */*",
}


# ── Custom exceptions ─────────────────────────────────────────────────────────

class RainVisionAuthError(Exception):
    """Raised when authentication fails (HTTP 401 or missing token)."""


class RainVisionApiError(Exception):
    """Raised for all non-auth API failures (network errors, unexpected status)."""


# ── API client ────────────────────────────────────────────────────────────────

class RainVisionApi:
    """Async HTTP client for the Rain Vision irrigation cloud API.

    Wraps every known endpoint and provides convenience methods that
    combine multiple calls (fetch → patch → save) for program editing.

    The Bearer token is stored internally after authenticate() and
    automatically included in subsequent requests via _auth_headers().

    Usage:
        session = aiohttp.ClientSession()
        api = RainVisionApi(session)
        token = await api.authenticate("user@example.com", "password")
        places = await api.get_places()
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client.

        Args:
            session: An aiohttp ClientSession managed by the caller.
        """
        self._session = session
        self._token: str | None = None

    # ── Token helpers ─────────────────────────────────────────────────────────

    @property
    def token(self) -> str | None:
        """Return the current Bearer token, or None if not authenticated."""
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        """Set the Bearer token directly (e.g. from a stored config entry)."""
        self._token = value

    def _auth_headers(self) -> dict[str, str]:
        """Return HEADERS_BASE extended with the Authorization header."""
        headers = dict(HEADERS_BASE)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # ── Authentication ────────────────────────────────────────────────────────

    async def authenticate(self, email: str, password: str) -> str:
        """Log in with email/password and return a new api_token.

        Calls POST /api/v5/token with a randomly generated device_name
        (required by the API to identify the client session).

        Args:
            email:    Rain Vision account email.
            password: Rain Vision account password.

        Returns:
            The api_token string to use as Bearer token.

        Raises:
            RainVisionAuthError: On HTTP 401 or missing token in response.
            RainVisionApiError:  On network errors or unexpected HTTP status.
        """
        payload = {
            "email":       email,
            "password":    password,
            "device_name": f"web-{uuid.uuid4()}",
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/token",
                json=payload,
                headers=HEADERS_BASE,
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Invalid email or password")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /token")
                data = await resp.json()
                token = data.get("api_token")
                if not token:
                    raise RainVisionAuthError("Login succeeded but no api_token in response")
                self._token = token
                return token
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error during login: {err}") from err

    async def check_token(self) -> bool:
        """Check whether the stored token is still valid.

        Calls POST /api/v5/check-token. This is a lightweight probe that
        does not require sending credentials again.

        Returns:
            True if the server responds with HTTP 200, False otherwise.
        """
        if not self._token:
            return False
        try:
            async with self._session.post(
                f"{BASE_URL}/check-token",
                headers=self._auth_headers(),
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def ensure_authenticated(self, email: str, password: str) -> str:
        """Ensure a valid token exists, re-authenticating if necessary.

        Calls check_token() first. If the token is missing or expired,
        calls authenticate() to obtain a fresh one. This avoids an
        unnecessary login on every HA restart.

        Args:
            email:    Used only if re-authentication is needed.
            password: Used only if re-authentication is needed.

        Returns:
            The valid api_token string.

        Raises:
            RainVisionAuthError: If (re-)authentication fails.
            RainVisionApiError:  On network errors.
        """
        if not await self.check_token():
            _LOGGER.info("Rain Vision: token missing or expired, re-authenticating")
            return await self.authenticate(email, password)
        return self._token  # type: ignore[return-value]

    # ── Data fetching ─────────────────────────────────────────────────────────

    async def get_places(self) -> list[dict]:
        """Fetch all places with their clouds and devices.

        Calls POST /api/v5/GetPlaces. Each place contains:
          - clouds  : list of Nuvola Vision hub dicts
          - devices : list of Pure Vision controller dicts (inside each cloud)
          - meteo   : current weather at the place location

        Returns:
            Flat list combining self_places and shared places.

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network or server errors.
        """
        try:
            async with self._session.post(
                f"{BASE_URL}/GetPlaces",
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /GetPlaces")
                data = await resp.json()
                return data.get("self_places", []) + data.get("places", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def get_device_realtime(
        self,
        device_puid: str,
        utc_offset_minutes: int = 120,
        force_refresh: bool = False,
    ) -> dict:
        """Fetch real-time device status from the Nuvola hub.

        Calls POST /api/v5/nuvola/device. Returns a rich response including:
          - data.status.battery   : battery level (int)
          - data.status.status    : 42-char hex string encoding zone/program state
          - data.status.pause     : pause schedule hex string
          - timestamp             : last update timestamp
          - device                : full device object (same as GetPlaces device)
          - cloud                 : parent Nuvola hub object with meteo data

        This endpoint provides fresher data than GetPlaces as it queries
        the Nuvola hub directly.

        Args:
            device_puid:         Device puid string (e.g. '1000005059').
            utc_offset_minutes:  UTC offset in minutes for the device timezone (default 120 = UTC+2).
            force_refresh:       If True, forces the hub to re-query the device via BLE.

        Returns:
            The full response dict from the API.

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network or server errors.
        """
        payload = {
            "device_puid":        device_puid,
            "utcOffsetInMinutes": utc_offset_minutes,
            "forceRefresh":       force_refresh,
        }
        # Response structure (documented from live capture):
        # {
        #   "success": true,
        #   "timestamp": "2026-05-30T19:00:51.185141Z",  <- root-level last update
        #   "next_update": null,
        #   "data": {
        #     "success": true,
        #     "status": {
        #       "battery": 83,
        #       "status":  "000100...",   <- 42-char hex: zone/program state
        #       "pause":   "3804...",     <- pause schedule hex
        #       "settings": "...",
        #       "timestamp": { "MSG_ID": 2, "RESULT": 0, "ARGS": [] }
        #     }
        #   },
        #   "device": { ...full device object with cloud nested inside... }
        # }
        try:
            async with self._session.post(
                f"{BASE_URL}/nuvola/device",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /nuvola/device")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def get_device_program_list(self, puid: str) -> list[dict]:
        """Fetch the full irrigation program list for a device.

        Calls POST /api/v5/GetDeviceProgramList with the device puid and the
        local UTC offset (derived automatically from the system clock).

        Each program dict contains:
          - name     : letter 'A'–'H'
          - times    : up to 6 start slots [{time, active, hidden, records}]
          - zones    : [{id, progressive, name, duration (seconds)}]
          - cycle    : repeat frequency as string in hours (e.g. '48')
          - weekdays : [{index, name, isChecked}]
          - type     : 'cycle' or other
          - active   : bool

        Args:
            puid: Device puid string (e.g. '1000005059').

        Returns:
            List of program dicts.

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network or server errors.
        """
        tz_offset = datetime.datetime.now().astimezone().strftime("%z")
        # Format as 'GMT+0200' matching what the webapp sends
        offset_str = f"GMT{tz_offset[:3]}{tz_offset[3:]}"
        # Compute UTC offset in minutes
        import datetime as _dt
        tz_offset_minutes = int(_dt.datetime.now().astimezone().utcoffset().total_seconds() / 60)
        payload = {
            "id":         puid,
            "offset":     offset_str,
            "tzOffset":   tz_offset_minutes,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/GetDeviceProgramList",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /GetDeviceProgramList")
                data = await resp.json()
                return data.get("programs", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def get_zone_names(self, device_puid: str) -> list[dict]:
        """Fetch zone names for a device.

        Calls POST /api/v5/GetZoneNames.

        Args:
            device_puid: Device puid string (e.g. '1000005059').

        Returns:
            List of zone dicts with zone_progressive, default_name, custom_name.

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network or server errors.
        """
        try:
            async with self._session.post(
                f"{BASE_URL}/GetZoneNames",
                json={"device_puid": device_puid},
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /GetZoneNames")
                data = await resp.json()
                return data.get("device", {}).get("zonenames", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def get_program_names(self, device_puid: str) -> list[dict]:
        """Fetch program names for a device.

        Calls POST /api/v5/GetProgramNames.

        Args:
            device_puid: Device puid string (e.g. '1000005059').

        Returns:
            List of program dicts with program_progressive, default_name, custom_name.

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network or server errors.
        """
        try:
            async with self._session.post(
                f"{BASE_URL}/GetProgramNames",
                json={"device_puid": device_puid},
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /GetProgramNames")
                data = await resp.json()
                return data.get("device", {}).get("programnames", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    # ── Manual irrigation commands ────────────────────────────────────────────

    async def get_nuvola_scan(
        self,
        cloud_puid: str,
        force_refresh: bool = False,
        utc_offset_minutes: int = 120,
    ) -> list[dict]:
        """Scan all BLE devices visible to the Nuvola hub.

        Calls POST /api/v5/nuvola/scan/full. Returns a list of peer dicts,
        each representing a BLE device in range of the hub. Each peer has:
          - puid        : device puid (int)
          - rssi        : BLE signal strength (int, higher = better)
          - battery     : battery level (int %)
          - paired      : whether the device is paired to this cloud
          - fw          : firmware version string
          - hwid        : hardware version int
          - devicetype  : device type object
          - device      : full device object (same structure as GetPlaces)
          - mdata       : raw BLE manufacturer data hex string
          - timestamp   : scan timestamp (at response root)

        Args:
            cloud_puid:          Nuvola hub puid (e.g. '2000001121').
            force_refresh:       If True, forces a new BLE scan.
            utc_offset_minutes:  UTC offset in minutes (default 120 = UTC+2).

        Returns:
            List of peer dicts from the scan response.

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network or server errors.
        """
        payload = {
            "cloud_puid":         cloud_puid,
            "scan_type":          1,
            "forceRefresh":       force_refresh,
            "utcOffsetInMinutes": utc_offset_minutes,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/nuvola/scan/full",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /nuvola/scan/full")
                data = await resp.json()
                return data.get("peers", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def manual_start_zone(
        self,
        device_puid: str,
        zone_progressive: int,
        duration_minutes: int = 10,
    ) -> bool:
        """Start manual irrigation on a specific zone.

        Calls POST /api/v5/nuvola/device/write with commandName=StartManualMode.
        Confirmed payload structure from live HAR capture:
        {
          "device_puid": "1000005059",
          "utcOffsetInMinutes": 120,
          "SaveManualStatus": true,
          "cancel": "ManualMode",
          "commandName": "StartManualMode",
          "manualZone": 4,              <- zone progressive index (1-4, not bitmask)
          "commands": [
            {"service": "F000", "characteristic": "F001", "values": ["06"]},
            {"service": "E000", "characteristic": "E005", "values": ["<hex>"]},
            {"service": "F000", "characteristic": "F001", "values": ["05"]}
          ]
        }

        The hex string in commands[1].values[0] encodes the zone and duration:
        - Byte 7 (offset 14): duration in seconds (e.g. 0x78 = 120 = 2 min)
        - Duration formula confirmed: duration_seconds = duration_minutes * 60
        - For durations > 255 seconds (> ~4 min): uses 2-byte little-endian
          at bytes 7-8. TODO: confirm with >4 min capture.

        Args:
            device_puid:      Pure Vision puid string (e.g. '1000005059').
            zone_progressive: Zone progressive index (1=Zone1, 2=Zone2, 3=Zone3, 4=Zone4).
            duration_minutes: Irrigation duration in minutes (default 10).

        Returns:
            True if the API accepted the command (success=true in response).

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network errors.
        """
        import datetime as _dt
        tz_offset = int(_dt.datetime.now().astimezone().utcoffset().total_seconds() / 60)

        # Build the hex command string encoding duration.
        # 128 bytes total = 256 hex chars.
        # Bytes 6-7 encode duration in seconds as big-endian uint16:
        # confirmed from live captures:
        #   2 min  = 120  sec = 0x0078 -> "0000000000000078..."
        #   10 min = 600  sec = 0x0258 -> "0000000000000258..."
        duration_seconds = duration_minutes * 60
        dur_hi = (duration_seconds >> 8) & 0xFF
        dur_lo = duration_seconds & 0xFF
        hex_cmd = (
            "000000000000"           # bytes 0-5: zeros
            + f"{dur_hi:02x}"        # byte 6: duration high byte
            + f"{dur_lo:02x}"        # byte 7: duration low byte
            + "00" * 56              # bytes 8-63: zeros
        )

        payload = {
            "device_puid":        device_puid,
            "utcOffsetInMinutes": tz_offset,
            "SaveManualStatus":   True,
            "cancel":             "ManualMode",
            "commandName":        "StartManualMode",
            "manualZone":         zone_progressive,
            "commands": [
                {"service": "F000", "characteristic": "F001", "values": ["06"]},
                {"service": "E000", "characteristic": "E005", "values": [hex_cmd]},
                {"service": "F000", "characteristic": "F001", "values": ["05"]},
            ],
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/nuvola/device/write",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /nuvola/device/write")
                data = await resp.json()
                return bool(data.get("success"))
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def manual_stop(self, device_puid: str) -> bool:
        """Stop all manual irrigation on a device.

        Calls POST /api/v5/nuvola/device/write with commandName=StopManualMode.
        Confirmed payload from live HAR capture:
        {
          "device_puid": "1000005059",
          "utcOffsetInMinutes": 120,
          "cancel": "ManualMode",
          "commandName": "StopManualMode",
          "commands": [{"service": "F000", "characteristic": "F001", "values": ["06", "04"]}]
        }

        Args:
            device_puid: Pure Vision puid string (e.g. '1000005059').

        Returns:
            True if the API accepted the command (success=true in response).

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network errors.
        """
        import datetime as _dt
        tz_offset = int(_dt.datetime.now().astimezone().utcoffset().total_seconds() / 60)
        payload = {
            "device_puid":        device_puid,
            "utcOffsetInMinutes": tz_offset,
            "cancel":             "ManualMode",
            "commandName":        "StopManualMode",
            "commands": [
                {"service": "F000", "characteristic": "F001", "values": ["06", "04"]}
            ],
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/nuvola/device/write",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP {resp.status} on /nuvola/device/write")
                data = await resp.json()
                return bool(data.get("success"))
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    # ── Program writing ───────────────────────────────────────────────────────

    async def set_device_programs(self, device_puid: str, programs: list[dict]) -> bool:
        """Save the complete programs list for a device.

        Calls POST /api/v5/SetDeviceProgramsNuvola. The API requires ALL
        programs (A–H) to be sent together even if only one was modified.
        Read-only fields are stripped before sending.

        Args:
            device_puid: Device puid string (e.g. '1000005059').
            programs:    Full list from get_device_program_list() with modifications.

        Returns:
            True if the API accepted the update (HTTP 200).

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network errors.
        """
        # Strip read-only fields the write endpoint does not accept.
        # Also normalise time strings: programs E-H may have JS date strings
        # like "Sat May 30 2026 00:00:00 GMT+0200" instead of "HH:MM".
        import re as _re
        _hhmm = _re.compile(r'^\d{2}:\d{2}$')

        def _normalise_time(raw: str) -> str:
            if raw and _hhmm.match(raw):
                return raw
            return "00:00"

        # Only send programs A-D; E-H are not yet supported
        supported = {"A", "B", "C", "D"}
        clean = []
        for prog in programs:
            if prog.get("name") not in supported:
                continue
            clean.append({
                "name":     prog["name"],
                "times":    [
                    {
                        "time":   _normalise_time(t.get("time", "00:00")),
                        "active": t.get("active", False),
                        "hidden": t.get("hidden", False),
                    }
                    for t in prog.get("times", [])
                ],
                "zones":    [
                    {"id": z["id"], "progressive": z["progressive"], "duration": z.get("duration", 0)}
                    for z in prog.get("zones", [])
                ],
                "type":     prog.get("type", "cycle"),
                "cycle":    prog.get("cycle", "6"),
                "weekdays": prog.get("weekdays", []),
                "even":     prog.get("even", "253"),
                "calendar": prog.get("calendar"),
                "active":   prog.get("active", True),
            })
        # Compute UTC offset in minutes from local timezone
        import datetime as _dt
        tz_offset_minutes = int(_dt.datetime.now().astimezone().utcoffset().total_seconds() / 60)

        payload = {
            "device_puid": device_puid,
            "programs":    clean,
            "overlapping": {"isSafe": True},
            "budget":      1,
            "tzOffset":    tz_offset_minutes,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/SetDeviceProgramsNuvola",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    # ── Convenience patch helpers (fetch → modify → save) ────────────────────

    async def set_zone_duration_in_program(
        self,
        device_puid: str,
        program_name: str,
        zone_id: int,
        duration_seconds: int,
    ) -> bool:
        """Update one zone's duration inside a program (read-modify-write).

        Args:
            device_puid:      Device puid (e.g. '1000005059').
            program_name:     Program letter ('A'–'H').
            zone_id:          Zone id as used by the API (1, 2, 4 or 8).
            duration_seconds: New duration in seconds (0 = disable zone).

        Returns:
            True on success.

        Raises:
            RainVisionApiError: If program or zone not found, or network error.
        """
        programs = await self.get_device_program_list(device_puid)
        patched = False
        for prog in programs:
            if prog.get("name") == program_name:
                for zone in prog.get("zones", []):
                    if zone.get("id") == zone_id:
                        zone["duration"] = duration_seconds
                        patched = True
                        break
        if not patched:
            raise RainVisionApiError(f"Program '{program_name}' or zone id {zone_id} not found")
        return await self.set_device_programs(device_puid, programs)

    async def set_program_start_time(
        self,
        device_puid: str,
        program_name: str,
        time_index: int,
        time: str,
        active: bool,
    ) -> bool:
        """Update a single start-time slot within a program (read-modify-write).

        Each program has up to 6 time slots (index 0–5).

        Args:
            device_puid:  Device puid.
            program_name: Program letter ('A'–'H').
            time_index:   Slot index (0–5).
            time:         Start time in 'HH:MM' format.
            active:       Whether this slot is enabled.

        Returns:
            True on success.

        Raises:
            RainVisionApiError: If program or slot index not found, or network error.
        """
        programs = await self.get_device_program_list(device_puid)
        patched = False
        for prog in programs:
            if prog.get("name") == program_name:
                times = prog.get("times", [])
                if time_index >= len(times):
                    raise RainVisionApiError(
                        f"Time slot index {time_index} out of range for program {program_name}"
                    )
                times[time_index]["time"]   = time
                times[time_index]["active"] = active
                patched = True
                break
        if not patched:
            raise RainVisionApiError(f"Program '{program_name}' not found")
        return await self.set_device_programs(device_puid, programs)

    async def set_program_cycle(
        self,
        device_puid: str,
        program_name: str,
        cycle_hours: int,
    ) -> bool:
        """Update the repeat frequency of a program (read-modify-write).

        Args:
            device_puid:  Device puid.
            program_name: Program letter ('A'–'H').
            cycle_hours:  Repeat interval in hours (e.g. 48 = every 2 days).

        Returns:
            True on success.

        Raises:
            RainVisionApiError: If program not found, or network error.
        """
        programs = await self.get_device_program_list(device_puid)
        patched = False
        for prog in programs:
            if prog.get("name") == program_name:
                prog["cycle"] = str(cycle_hours)
                patched = True
                break
        if not patched:
            raise RainVisionApiError(f"Program '{program_name}' not found")
        return await self.set_device_programs(device_puid, programs)

    async def set_program_weekdays(
        self,
        device_puid: str,
        program_name: str,
        active_day_indexes: list[int],
    ) -> bool:
        """Update which weekdays a program runs (read-modify-write).

        Day index mapping: 1=Sun, 2=Mon, 3=Tue, 4=Wed, 5=Thu, 6=Fri, 7=Sat.

        Args:
            device_puid:        Device puid.
            program_name:       Program letter ('A'–'H').
            active_day_indexes: Day indexes to enable (others are disabled).

        Returns:
            True on success.

        Raises:
            RainVisionApiError: If program not found, or network error.
        """
        programs = await self.get_device_program_list(device_puid)
        patched = False
        for prog in programs:
            if prog.get("name") == program_name:
                for day in prog.get("weekdays", []):
                    day["isChecked"] = day["index"] in active_day_indexes
                patched = True
                break
        if not patched:
            raise RainVisionApiError(f"Program '{program_name}' not found")
        return await self.set_device_programs(device_puid, programs)

    async def set_program_active(
        self,
        cloud_id: int,
        device_id: int,
        program: str,
        active: bool,
    ) -> bool:
        """Enable or disable a program without modifying its configuration.

        Calls POST /api/v5/SetProgramActive.

        Args:
            cloud_id:  ID of the parent Nuvola hub.
            device_id: ID of the Pure Vision device.
            program:   Program letter ('A'–'H').
            active:    True to enable, False to disable.

        Returns:
            True if the API accepted the command (HTTP 200).

        Raises:
            RainVisionAuthError: On HTTP 401.
            RainVisionApiError:  On network errors.
        """
        payload = {
            "cloud_id":  cloud_id,
            "device_id": device_id,
            "program":   program,
            "active":    active,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/SetProgramActive",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err
