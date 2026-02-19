"""Tests for MarstekRelayClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.marstek.pymarstek.relay_client import MarstekRelayClient


def make_mock_response(
    json_data: dict[str, Any],
    status: int = 200,
) -> MagicMock:
    """Build a mock aiohttp response."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def make_mock_session(response: MagicMock) -> MagicMock:
    """Build a mock aiohttp ClientSession."""
    session = MagicMock(spec=aiohttp.ClientSession)
    session.get = MagicMock(return_value=response)
    session.post = MagicMock(return_value=response)
    return session


class TestMarstekRelayClientSetup:
    """Tests for async_setup."""

    async def test_setup_success(self) -> None:
        """Test successful setup when relay responds with 200."""
        resp = make_mock_response({"status": "ok", "version": "1.0.0"})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        await client.async_setup()

        session.get.assert_called_once()
        call_url = session.get.call_args[0][0]
        assert call_url == "http://relay:8765/health"

    async def test_setup_with_api_key(self) -> None:
        """Test setup sends X-API-Key header when api_key is set."""
        resp = make_mock_response({"status": "ok"})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session, api_key="secret")
        await client.async_setup()

        call_kwargs = session.get.call_args[1]
        assert call_kwargs["headers"]["X-API-Key"] == "secret"

    async def test_setup_auth_failure(self) -> None:
        """Test setup raises ValueError on 401 response."""
        resp = make_mock_response({"error": "Unauthorized"}, status=401)
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session, api_key="wrong")
        with pytest.raises(ValueError, match="rejected the API key"):
            await client.async_setup()

    async def test_setup_connection_error(self) -> None:
        """Test setup raises OSError when relay is unreachable."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.get = MagicMock(side_effect=aiohttp.ClientConnectionError("refused"))

        client = MarstekRelayClient("http://relay:8765", session)
        with pytest.raises(OSError, match="Cannot reach relay server"):
            await client.async_setup()

    async def test_cleanup_noop(self) -> None:
        """Test cleanup is a no-op (session managed by HA)."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = MarstekRelayClient("http://relay:8765", session)
        await client.async_cleanup()  # Should not raise


class TestPollingPause:
    """Tests for polling pause/resume state."""

    async def test_pause_and_resume(self) -> None:
        """Test polling pause/resume cycle."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = MarstekRelayClient("http://relay:8765", session)

        assert not client.is_polling_paused("1.2.3.4")

        await client.pause_polling("1.2.3.4")
        assert client.is_polling_paused("1.2.3.4")

        await client.resume_polling("1.2.3.4")
        assert not client.is_polling_paused("1.2.3.4")

    async def test_pause_different_devices_independent(self) -> None:
        """Test that pause state is independent per device."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = MarstekRelayClient("http://relay:8765", session)

        await client.pause_polling("1.2.3.4")
        assert not client.is_polling_paused("5.6.7.8")


class TestSendRequest:
    """Tests for send_request."""

    async def test_send_request_success(self) -> None:
        """Test successful command forwarding."""
        device_response = {"id": 1, "result": {"mode": "Auto"}}
        resp = make_mock_response({"response": device_response})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        command = '{"id":1,"method":"ES.GetMode","params":{"id":0}}'
        result = await client.send_request(command, "1.2.3.4", 30000)

        assert result == device_response

    async def test_send_request_timeout(self) -> None:
        """Test send_request raises TimeoutError on relay timeout response."""
        resp = make_mock_response({"error": "No response from device"}, status=504)
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        command = '{"id":1,"method":"ES.GetMode","params":{"id":0}}'
        with pytest.raises(TimeoutError):
            await client.send_request(command, "1.2.3.4", 30000)

    async def test_send_request_http_error(self) -> None:
        """Test send_request raises OSError on HTTP connectivity failure."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("refused"))

        client = MarstekRelayClient("http://relay:8765", session)
        command = '{"id":1,"method":"ES.GetMode","params":{"id":0}}'
        with pytest.raises(OSError, match="Relay HTTP error"):
            await client.send_request(command, "1.2.3.4", 30000)

    async def test_send_request_quiet_on_timeout(self) -> None:
        """Test quiet_on_timeout suppresses timeout warning log."""
        resp = make_mock_response({"error": "timeout"}, status=504)
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        command = '{"id":1,"method":"ES.GetMode","params":{"id":0}}'
        with pytest.raises(TimeoutError):
            await client.send_request(
                command, "1.2.3.4", 30000, quiet_on_timeout=True
            )

    async def test_send_request_validation_error(self) -> None:
        """Test send_request raises ValidationError for invalid messages."""
        from custom_components.marstek.pymarstek.validators import ValidationError

        session = MagicMock(spec=aiohttp.ClientSession)
        client = MarstekRelayClient("http://relay:8765", session)

        # Invalid method name
        bad_command = '{"id":1,"method":"Invalid.Method","params":{}}'
        with pytest.raises(ValidationError):
            await client.send_request(bad_command, "1.2.3.4", 30000)


class TestGetDeviceStatus:
    """Tests for get_device_status."""

    async def test_get_device_status_success(self) -> None:
        """Test successful device status retrieval via relay /api/status."""
        relay_status = {
            "device_mode": "Auto",
            "battery_soc": 75,
            "battery_power": -500,
            "ongrid_power": 200,
            "ct_state": 1,
            "ct_connected": True,
            "em_total_power": 300,
        }
        resp = make_mock_response({"status": relay_status})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        status = await client.get_device_status(
            "1.2.3.4",
            include_pv=False,
            include_wifi=False,
            include_em=True,
            include_bat=False,
        )

        assert isinstance(status, dict)
        assert status.get("has_fresh_data") is True

    async def test_get_device_status_relay_error(self) -> None:
        """Test get_device_status raises TimeoutError on relay error response."""
        resp = make_mock_response({"error": "device timeout"}, status=504)
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        with pytest.raises(TimeoutError):
            await client.get_device_status("1.2.3.4")

    async def test_get_device_status_http_error(self) -> None:
        """Test get_device_status raises OSError on HTTP connectivity failure."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("refused"))

        client = MarstekRelayClient("http://relay:8765", session)
        with pytest.raises(OSError, match="Relay HTTP error"):
            await client.get_device_status("1.2.3.4")

    async def test_get_device_status_empty_relay_status(self) -> None:
        """Test get_device_status returns dict with has_fresh_data=False when empty."""
        resp = make_mock_response({"status": {}})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        status = await client.get_device_status("1.2.3.4")

        assert status.get("has_fresh_data") is False

    async def test_get_device_status_with_pv_wifi_bat(self) -> None:
        """Test get_device_status with all optional fields."""
        relay_status = {
            "device_mode": "Auto",
            "battery_soc": 80,
            "battery_power": 0,
            "pv1_power": 500,
            "wifi_rssi": -65,
            "bat_temp": 28.0,
            "ct_state": 1,
        }
        resp = make_mock_response({"status": relay_status})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        status = await client.get_device_status(
            "1.2.3.4",
            include_pv=True,
            include_wifi=True,
            include_em=True,
            include_bat=True,
        )

        assert isinstance(status, dict)
        assert status.get("has_fresh_data") is True


class TestDiscoverDevices:
    """Tests for discover_devices."""

    async def test_discover_devices_success(self) -> None:
        """Test successful device discovery via relay."""
        devices: list[dict[str, Any]] = [
            {
                "ip": "1.2.3.4",
                "ble_mac": "aabbccddeeff",
                "device_type": "VenusE 3.0",
            }
        ]
        resp = make_mock_response({"devices": devices})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        result = await client.discover_devices()

        assert len(result) == 1
        assert result[0]["ip"] == "1.2.3.4"

    async def test_discover_devices_empty(self) -> None:
        """Test discovery returns empty list when no devices found."""
        resp = make_mock_response({"devices": []})
        session = make_mock_session(resp)

        client = MarstekRelayClient("http://relay:8765", session)
        result = await client.discover_devices()

        assert result == []

    async def test_discover_devices_http_error(self) -> None:
        """Test discover_devices raises OSError on HTTP failure."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("refused"))

        client = MarstekRelayClient("http://relay:8765", session)
        with pytest.raises(OSError, match="Relay discovery failed"):
            await client.discover_devices()


class TestDiagnostics:
    """Tests for diagnostics methods."""

    def test_get_command_stats_returns_empty(self) -> None:
        """Test get_command_stats_for_ip returns empty dict (relay mode)."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = MarstekRelayClient("http://relay:8765", session)
        stats = client.get_command_stats_for_ip("1.2.3.4")
        assert stats == {}

    async def test_record_stat_tracks_success(self) -> None:
        """Test _record_stat increments success counter."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = MarstekRelayClient("http://relay:8765", session)

        client._record_stat("ES.GetMode", success=True, timeout=False)
        assert client._command_stats["ES.GetMode"]["total_success"] == 1

        client._record_stat("ES.GetMode", success=False, timeout=True)
        assert client._command_stats["ES.GetMode"]["total_timeouts"] == 1
