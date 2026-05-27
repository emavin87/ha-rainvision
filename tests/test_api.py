"""Unit tests for RainvisionApiClient."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.rainvision.api import (
    RainvisionApiClient,
    RainvisionAuthError,
    RainvisionConnectionError,
)


@pytest.fixture
def mock_session():
    """Return a minimal aiohttp.ClientSession mock."""
    session = MagicMock()
    return session


def _make_response(status: int, json_data: dict):
    """Build a context-manager mock that mimics aiohttp's response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestAuthenticate:
    async def test_returns_token_on_success(self, mock_session):
        mock_session.post.return_value = _make_response(
            200, {"token": "abc123", "user": {}}
        )
        client = RainvisionApiClient(mock_session)
        token = await client.authenticate("user@example.com", "password")
        assert token == "abc123"
        assert client.token == "abc123"

    async def test_raises_auth_error_when_no_token(self, mock_session):
        mock_session.post.return_value = _make_response(200, {"user": {}})
        client = RainvisionApiClient(mock_session)
        with pytest.raises(RainvisionAuthError):
            await client.authenticate("user@example.com", "wrong")

    async def test_raises_auth_error_on_401(self, mock_session):
        mock_session.post.return_value = _make_response(401, {})
        client = RainvisionApiClient(mock_session)
        with pytest.raises(RainvisionAuthError):
            await client.authenticate("user@example.com", "bad")

    async def test_raises_connection_error_on_500(self, mock_session):
        mock_session.post.return_value = _make_response(500, {})
        client = RainvisionApiClient(mock_session)
        with pytest.raises(RainvisionConnectionError):
            await client.authenticate("user@example.com", "pass")


class TestCheckToken:
    async def test_returns_true_when_valid(self, mock_session):
        mock_session.post.return_value = _make_response(200, {"valid": True})
        client = RainvisionApiClient(mock_session, token="tok")
        assert await client.check_token() is True

    async def test_returns_false_when_401(self, mock_session):
        mock_session.post.return_value = _make_response(401, {})
        client = RainvisionApiClient(mock_session, token="expired")
        assert await client.check_token() is False


class TestGetDeviceStatus:
    async def test_passes_correct_body(self, mock_session):
        mock_session.post.return_value = _make_response(200, {"success": True})
        client = RainvisionApiClient(mock_session, token="tok")
        await client.get_device_status("1000005059", utc_offset=120)

        call_kwargs = mock_session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert body["device_puid"] == "1000005059"
        assert body["utcOffsetInMinutes"] == 120
        assert body["forceRefresh"] is False
