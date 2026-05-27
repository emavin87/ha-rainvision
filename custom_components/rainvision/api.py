"""Rain Vision API client."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.rainvision.it/api/v5"
HEADERS_BASE = {
    "Content-Type": "application/json",
    "Content-Language": "it",
    "Accept": "application/json, text/plain, */*",
}


class RainVisionAuthError(Exception):
    """Authentication error."""


class RainVisionApiError(Exception):
    """Generic API error."""


class RainVisionApi:
    """Rain Vision REST API client."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._token: str | None = None

    @property
    def token(self) -> str | None:
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        self._token = value

    def _auth_headers(self) -> dict:
        headers = dict(HEADERS_BASE)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def authenticate(self, email: str, password: str) -> str:
        """Login via check-token and return api_token."""
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
                    raise RainVisionAuthError("Credenziali non valide")
                if resp.status != 200:
                    raise RainVisionApiError(f"Errore HTTP {resp.status}")
                data = await resp.json()
                token = data.get("api_token")
                if not token:
                    raise RainVisionAuthError("Token non ricevuto")
                self._token = token
                return token
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Errore di connessione: {err}") from err

    async def get_places(self) -> list[dict]:
        """Return list of places with clouds and devices."""
        try:
            async with self._session.post(
                f"{BASE_URL}/GetPlaces",
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token non valido o scaduto")
                if resp.status != 200:
                    raise RainVisionApiError(f"Errore HTTP {resp.status}")
                data = await resp.json()
                places = data.get("self_places", []) + data.get("places", [])
                return places
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Errore di connessione: {err}") from err

    async def manual_start_zone(
        self,
        cloud_id: int,
        device_id: int,
        zone: int,
        duration_minutes: int = 10,
    ) -> bool:
        """Start manual irrigation on a zone."""
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
                    raise RainVisionAuthError("Token non valido o scaduto")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Errore di connessione: {err}") from err

    async def manual_stop(
        self,
        cloud_id: int,
        device_id: int,
    ) -> bool:
        """Stop manual irrigation."""
        payload = {
            "cloud_id": cloud_id,
            "device_id": device_id,
        }
        try:
            async with self._session.post(
                f"{BASE_URL}/ManualStop",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 401:
                    raise RainVisionAuthError("Token non valido o scaduto")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Errore di connessione: {err}") from err

    async def set_program_active(
        self,
        cloud_id: int,
        device_id: int,
        program: str,
        active: bool,
    ) -> bool:
        """Enable or disable a program (A/B/C/D)."""
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
                    raise RainVisionAuthError("Token non valido o scaduto")
                return resp.status == 200
        except aiohttp.ClientError as err:
            raise RainVisionApiError(f"Errore di connessione: {err}") from err
