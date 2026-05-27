"""
Rain Vision API Client
======================
This module provides the low-level HTTP client for the Rain Vision REST API
(https://www.rainvision.it/api/v5).

It handles:
- Authentication (login + token validation)
- Fetching places, clouds, devices and their state
- Reading and writing irrigation programs
- Sending manual irrigation start/stop commands

All methods are async and use aiohttp for HTTP communication.
Errors are raised as RainVisionAuthError (auth failures) or
RainVisionApiError (network/server errors), so callers can
handle them distinctly.
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.rainvision.it/api/v5"

# Default headers sent with every request
HEADERS_BASE = {
    "Content-Type": "application/json",
    "Content-Language": "it",
    "Accept": "application/json, text/plain, */*",
}


class RainVisionAuthError(Exception):
    """Raised when authentication fails.

    This covers invalid credentials on login and expired/invalid tokens
    on subsequent API calls (HTTP 401 responses).
    """


class RainVisionApiError(Exception):
    """Raised for all non-auth API failures.

    This covers network errors, unexpected HTTP status codes,
    missing fields in responses, and invalid arguments passed
    to convenience methods.
    """


class RainVisionApi:
    """Async HTTP client for the Rain Vision irrigation API.

    Wraps all known API endpoints and provides convenience methods
    that combine multiple calls (e.g. fetch → patch → save).

    Usage:
        session = aiohttp.ClientSession()
        api = RainVisionApi(session)
        token = await api.authenticate("user@example.com", "password")
        places = await api.get_places()

    The token is stored internally and automatically included in all
    subsequent requests via the Authorization header.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client.

        Args:
            session: An aiohttp ClientSession to use for all HTTP requests.
                     The caller is responsible for its lifecycle.
        """
        self._session = session
        self._token: str | None = None

    # ── Token management ──────────────────────────────────────────────────────

    @property
    def token(self) -> str | None:
        """Return the current Bearer token, or None if not authenticated."""
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        """Set the Bearer token directly (e.g. from a stored config entry)."""
        self._token = value

    def _auth_headers(self) -> dict:
        """Build request headers with the Authorization Bearer token.

        Returns a copy of HEADERS_BASE with the Authorization header
        added if a token is available.
        """
        headers = dict(HEADERS_BASE)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # ── Authentication ────────────────────────────────────────────────────────

    async def authenticate(self, email: str, password: str) -> str:
        """Log in with email and password and return a new api_token.

        Calls POST /api/v5/token with the user credentials and a
        randomly generated device_name (required by the API to identify
        the client session).

        Args:
            email: The user's Rain Vision account email.
            password: The user's Rain Vision account password.

        Returns:
            The api_token string to be used as Bearer token.

        Raises:
            RainVisionAuthError: If credentials are invalid (HTTP 401)
                                 or the token is missing from the response.
            RainVisionApiError: On network errors or unexpected HTTP status.
        """
        device_name = f"web-{uuid.uuid4()}"
        payload = {
            "email": email,
            "password": password,
            "device_name": device_name,
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
                    raise RainVisionApiError(f"Unexpected HTTP status {resp.status}")
                data = await resp.json()
                token = data.get("api_token")
                if not token:
                    raise RainVisionAuthError("Login succeeded but no token in response")
                self._token = token
                return token
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error during login: {err}") from err

    async def check_token(self) -> bool:
        """Check whether the current token is still valid.

        Calls POST /api/v5/check-token with the stored Bearer token.
        This is a lightweight validity check that does not require
        sending credentials again.

        Returns:
            True if the token is valid (HTTP 200), False otherwise.
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
        """Ensure the client has a valid token, re-authenticating if needed.

        First checks the stored token with check_token(). If the token
        is missing or expired, calls authenticate() to obtain a new one.

        This is the preferred method to call at startup so that stored
        tokens are reused across Home Assistant restarts without
        unnecessarily triggering a new login.

        Args:
            email: Account email, used only if re-authentication is needed.
            password: Account password, used only if re-authentication is needed.

        Returns:
            The valid api_token string.

        Raises:
            RainVisionAuthError: If re-authentication fails.
            RainVisionApiError: On network errors.
        """
        valid = await self.check_token()
        if not valid:
            _LOGGER.info("Rain Vision token expired or missing, re-authenticating")
            return await self.authenticate(email, password)
        return self._token

    # ── Data fetching ─────────────────────────────────────────────────────────

    async def get_places(self) -> list[dict]:
        """Fetch all places (impianti) owned by the authenticated user.

        Calls POST /api/v5/GetPlaces. Each place contains:
        - Basic info (id, name, city, coordinates)
        - A list of 'clouds' (Nuvola Vision hub devices)
        - Each cloud contains a list of 'devices' (Pure Vision controllers)
        - Each device contains zone names, program names, battery level,
          firmware info, online status, and a 'manual' hex string encoding
          the current manual irrigation state.

        Returns:
            A flat list combining self_places and shared places.

        Raises:
            RainVisionAuthError: If the token is invalid (HTTP 401).
            RainVisionApiError: On network or server errors.
        """
        try:
            async with self._session.post(
                f"{BASE_URL}/GetPlaces",
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP status {resp.status}")
                data = await resp.json()
                # Merge owned places and shared places into a single list
                return data.get("self_places", []) + data.get("places", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def get_device_program_list(self, puid: str) -> list[dict]:
        """Fetch the full irrigation program list for a specific device.

        Calls POST /api/v5/GetDeviceProgramList. The response contains
        one entry for each program slot (A through H), each with:
        - name: program letter ('A', 'B', ...)
        - times: up to 6 start time slots [{active, time, records, hidden}]
        - zones: list of zone entries [{id, progressive, name, duration (seconds)}]
        - cycle: frequency string in hours (e.g. '48' = every 2 days)
        - weekdays: list of [{name, index, isChecked}]
        - type: 'cycle' or other schedule type
        - even: internal bitmask string

        The timezone offset is automatically derived from the system clock
        and passed to the API as required (e.g. 'GMT+02:00').

        Args:
            puid: The device's puid string (e.g. '1000005059').

        Returns:
            List of program dicts as described above.

        Raises:
            RainVisionAuthError: If the token is invalid.
            RainVisionApiError: On network or server errors.
        """
        tz_offset = datetime.datetime.now().astimezone().strftime("%z")
        offset_str = f"GMT{tz_offset[:3]}:{tz_offset[3:]}"
        payload = {"id": puid, "offset": offset_str}
        try:
            async with self._session.post(
                f"{BASE_URL}/GetDeviceProgramList",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                if resp.status != 200:
                    raise RainVisionApiError(f"Unexpected HTTP status {resp.status}")
                data = await resp.json()
                return data.get("programs", [])
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    # ── Manual irrigation commands ────────────────────────────────────────────

    async def manual_start_zone(
        self,
        cloud_id: int,
        device_id: int,
        zone: int,
        duration_minutes: int = 10,
    ) -> bool:
        """Start manual irrigation on a specific zone.

        Calls POST /api/v5/ManualStart. The command is routed through
        the Nuvola cloud hub (identified by cloud_id) to the Pure Vision
        device (device_id).

        Args:
            cloud_id: The id of the Nuvola hub that manages the device.
            device_id: The id of the Pure Vision device.
            zone: Zone number (1-based integer, e.g. 1 for zone 1).
            duration_minutes: How long to irrigate (default: 10 minutes).

        Returns:
            True if the API accepted the command (HTTP 200).

        Raises:
            RainVisionAuthError: If the token is invalid.
            RainVisionApiError: On network errors.
        """
        payload = {
            "cloud_id": cloud_id,
            "device_id": device_id,
            "zone": zone,
            "duration": duration_minutes,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/ManualStart",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    async def manual_stop(self, cloud_id: int, device_id: int) -> bool:
        """Stop any ongoing manual irrigation on a device.

        Calls POST /api/v5/ManualStop. This stops all manually running zones
        on the specified device immediately.

        Args:
            cloud_id: The id of the Nuvola hub.
            device_id: The id of the Pure Vision device.

        Returns:
            True if the API accepted the command (HTTP 200).

        Raises:
            RainVisionAuthError: If the token is invalid.
            RainVisionApiError: On network errors.
        """
        payload = {"cloud_id": cloud_id, "device_id": device_id}
        try:
            async with self._session.post(
                f"{BASE_URL}/ManualStop",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token invalid or expired")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Connection error: {err}") from err

    # ── Program writing ───────────────────────────────────────────────────────

    async def set_device_programs(self, device_puid: str, programs: list[dict]) -> bool:
        """Save the complete irrigation programs list for a device.

        Calls POST /api/v5/SetDeviceProgramsNuvola with the full programs
        payload. The API requires ALL programs (A-H) to be sent together,
        even if only one was modified. Read-only fields (e.g. zone 'name',
        time 'records') are stripped before sending.

        The payload structure is:
            {
                device_puid: str,
                programs: [
                    {
                        name: str,          # 'A' through 'H'
                        times: [{time, active, hidden}],
                        zones: [{id, progressive, duration}],
                        type: str,          # 'cycle'
                        cycle: str,         # hours as string, e.g. '48'
                        weekdays: [{index, name, isChecked}],
                        even: str,          # internal bitmask
                        calendar: null,
                        active: bool
                    }
                ],
                overlapping: {isSafe: true}
            }

        Args:
            device_puid: Device puid string (e.g. '1000005059').
            programs: Full list of program dicts, typically obtained from
                      get_device_program_list() with modifications applied.

        Returns:
            True if the API accepted the update (HTTP 200).

        Raises:
            RainVisionAuthError: If the token is invalid.
            RainVisionApiError: On network errors.
        """
        # Strip read-only fields the write API does not accept
        clean_programs = []
        for prog in programs:
            clean_zones = [
                {
                    "id": z["id"],
                    "progressive": z["progressive"],
                    "duration": z.get("duration", 0),
                }
                for z in prog.get("zones", [])
            ]
            clean_times = [
                {
                    "time": t.get("time"),
                    "active": t.get("active", False),
                    "hidden": t.get("hidden", False),
                }
                for t in prog.get("times", [])
            ]
            clean_programs.append({
                "name": prog["name"],
                "times": clean_times,
                "zones": clean_zones,
                "type": prog.get("type", "cycle"),
                "cycle": prog.get("cycle", "6"),
                "weekdays": prog.get("weekdays", []),
                "even": prog.get("even", "253"),
                "calendar": prog.get("calendar"),
                "active": prog.get("active", True),
            })

        payload = {
            "device_puid": device_puid,
            "programs": clean_programs,
            "overlapping": {"isSafe": True},
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

    # ── Convenience patch methods (fetch → modify → save) ─────────────────────

    async def set_zone_duration_in_program(
        self,
        device_puid: str,
        program_name: str,
        zone_id: int,
        duration_seconds: int,
    ) -> bool:
        """Update the irrigation duration for one zone within a program.

        Convenience method that performs a full read-modify-write cycle:
        1. Fetches the current program list with get_device_program_list()
        2. Finds the target program and zone by name/id
        3. Updates the duration field
        4. Saves the full programs list with set_device_programs()

        Args:
            device_puid: Device puid (e.g. '1000005059').
            program_name: Program letter ('A' through 'H').
            zone_id: Zone id as used by the API (1, 2, 4, or 8 for zones 1-4).
            duration_seconds: New duration in seconds (0 disables the zone).

        Returns:
            True if the save succeeded.

        Raises:
            RainVisionApiError: If the program or zone is not found,
                                or on network errors.
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
            raise RainVisionApiError(
                f"Program '{program_name}' or zone id {zone_id} not found"
            )
        return await self.set_device_programs(device_puid, programs)

    async def set_program_start_time(
        self,
        device_puid: str,
        program_name: str,
        time_index: int,
        time: str,
        active: bool,
    ) -> bool:
        """Update a start time slot within a program.

        Each program has up to 6 time slots (index 0-5). This method
        performs a read-modify-write cycle to update a single slot's
        start time and active state without touching the other slots.

        Args:
            device_puid: Device puid (e.g. '1000005059').
            program_name: Program letter ('A' through 'H').
            time_index: Which time slot to update (0 = first, up to 5).
            time: Start time string in 'HH:MM' format (e.g. '06:30').
            active: True to enable this time slot, False to disable it.

        Returns:
            True if the save succeeded.

        Raises:
            RainVisionApiError: If the program is not found, the index is
                                out of range, or on network errors.
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
                times[time_index]["time"] = time
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
        """Update the cycle frequency of a program.

        The cycle defines how often the program repeats, expressed in hours.
        Common values: 6 (4x/day), 24 (daily), 48 (every 2 days).

        Performs a read-modify-write cycle.

        Args:
            device_puid: Device puid (e.g. '1000005059').
            program_name: Program letter ('A' through 'H').
            cycle_hours: Repeat interval in hours (e.g. 48 = every 2 days).

        Returns:
            True if the save succeeded.

        Raises:
            RainVisionApiError: If the program is not found or on network errors.
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
        """Update which weekdays a program is scheduled to run.

        Performs a read-modify-write cycle, enabling only the days
        whose indexes appear in active_day_indexes and disabling the rest.

        Day index mapping (matches Rain Vision API):
            1 = Sunday, 2 = Monday, 3 = Tuesday, 4 = Wednesday,
            5 = Thursday, 6 = Friday, 7 = Saturday

        Args:
            device_puid: Device puid (e.g. '1000005059').
            program_name: Program letter ('A' through 'H').
            active_day_indexes: List of day indexes to enable
                                (e.g. [2, 4, 6] = Mon/Wed/Fri).

        Returns:
            True if the save succeeded.

        Raises:
            RainVisionApiError: If the program is not found or on network errors.
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
        """Enable or disable a program (A-H) on a device.

        Calls POST /api/v5/SetProgramActive. This is a direct toggle
        that does not require sending the full programs payload.

        Args:
            cloud_id: The id of the Nuvola hub.
            device_id: The id of the Pure Vision device.
            program: Program letter to toggle ('A' through 'H').
            active: True to enable the program, False to disable it.

        Returns:
            True if the API accepted the command (HTTP 200).

        Raises:
            RainVisionAuthError: If the token is invalid.
            RainVisionApiError: On network errors.
        """
        payload = {
            "cloud_id": cloud_id,
            "device_id": device_id,
            "program": program,
            "active": active,
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
