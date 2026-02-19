"""Tests for relay server config flow steps."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.device_registry import format_mac
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.marstek.const import (
    CONF_CONNECTION_TYPE,
    CONF_RELAY_API_KEY,
    CONF_RELAY_URL,
    CONNECTION_TYPE_RELAY,
    DOMAIN,
)

from tests.conftest import create_mock_client, create_mock_scanner


_RELAY_URL = "http://relay-server:8765"


def _mock_relay_health(reachable: bool = True) -> Any:
    """Patch _check_relay_health in config_flow."""
    return patch(
        "custom_components.marstek.config_flow._check_relay_health",
        AsyncMock(return_value=reachable),
    )


def _mock_relay_discover(
    devices: list[dict[str, Any]], error: Exception | None = None
) -> Any:
    """Patch _discover_via_relay in config_flow."""
    if error:
        return patch(
            "custom_components.marstek.config_flow._discover_via_relay",
            AsyncMock(side_effect=error),
        )
    return patch(
        "custom_components.marstek.config_flow._discover_via_relay",
        AsyncMock(return_value=devices),
    )


@contextmanager
def patch_relay_integration(client: MagicMock | None = None) -> Any:
    """Patch relay client creation and scanner for integration tests."""
    mock_client = client or create_mock_client()
    mock_scanner = create_mock_scanner()
    with (
        patch("custom_components.marstek.scanner.MarstekScanner._scanner", None),
        patch(
            "custom_components.marstek._create_relay_client",
            AsyncMock(return_value=mock_client),
        ),
        patch(
            "custom_components.marstek.scanner.MarstekScanner.async_get",
            return_value=mock_scanner,
        ),
    ):
        yield mock_client, mock_scanner


async def _init_and_select_relay(hass: HomeAssistant) -> dict[str, Any]:
    """Start user flow and choose relay connection type."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_CONNECTION_TYPE: CONNECTION_TYPE_RELAY},
    )
    return result  # type: ignore[return-value]


async def test_relay_flow_server_not_reachable(hass: HomeAssistant) -> None:
    """Test relay flow shows error when relay server is not reachable."""
    result = await _init_and_select_relay(hass)
    assert result["step_id"] == "relay"

    with _mock_relay_health(reachable=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: ""},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "relay"
    assert result["errors"] == {"base": "cannot_connect_relay"}


async def test_relay_flow_server_reachable_no_devices(hass: HomeAssistant) -> None:
    """Test relay flow redirects to relay_manual when no devices found."""
    result = await _init_and_select_relay(hass)
    assert result["step_id"] == "relay"

    with _mock_relay_health(reachable=True), _mock_relay_discover([]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: ""},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "relay_manual"


async def test_relay_flow_server_discovery_failure(hass: HomeAssistant) -> None:
    """Test relay flow shows error when relay discovery fails."""
    import aiohttp  # noqa: PLC0415

    result = await _init_and_select_relay(hass)
    assert result["step_id"] == "relay"

    with (
        _mock_relay_health(reachable=True),
        _mock_relay_discover([], error=aiohttp.ClientConnectionError("refused")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: ""},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "relay"
    assert result["errors"] == {"base": "cannot_connect_relay"}


async def test_relay_flow_device_selection_success(hass: HomeAssistant) -> None:
    """Test complete relay flow from server config to device creation."""
    devices = [
        {
            "ip": "192.168.10.50",
            "ble_mac": "AA:BB:CC:DD:EE:FF",
            "mac": "AA:BB:CC:DD:EE:FF",
            "wifi_mac": "11:22:33:44:55:66",
            "device_type": "VenusE 3.0",
            "version": 111,
            "wifi_name": "marstek",
            "model": "VenusE 3.0",
            "firmware": "111",
        }
    ]

    result = await _init_and_select_relay(hass)
    assert result["step_id"] == "relay"

    with _mock_relay_health(reachable=True), _mock_relay_discover(devices):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: ""},
        )

    assert result["step_id"] == "relay_select"

    with patch_relay_integration():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"device": "0"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_RELAY
    assert result["data"][CONF_RELAY_URL] == _RELAY_URL
    assert result["data"]["host"] == "192.168.10.50"
    assert format_mac(result["data"]["ble_mac"]) == "aa:bb:cc:dd:ee:ff"


async def test_relay_flow_with_api_key(hass: HomeAssistant) -> None:
    """Test relay flow stores the API key in entry data."""
    devices = [
        {
            "ip": "192.168.10.50",
            "ble_mac": "AA:BB:CC:DD:EE:FF",
            "mac": "AA:BB:CC:DD:EE:FF",
            "wifi_mac": "11:22:33:44:55:66",
            "device_type": "VenusE 3.0",
            "version": 111,
            "wifi_name": "marstek",
            "model": "VenusE 3.0",
            "firmware": "111",
        }
    ]

    result = await _init_and_select_relay(hass)

    with _mock_relay_health(reachable=True), _mock_relay_discover(devices):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: "mysecret"},
        )

    assert result["step_id"] == "relay_select"

    with patch_relay_integration():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"device": "0"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"].get(CONF_RELAY_API_KEY) == "mysecret"


async def test_relay_manual_flow_success(hass: HomeAssistant) -> None:
    """Test relay manual entry creates config entry with relay data."""
    result = await _init_and_select_relay(hass)

    with _mock_relay_health(reachable=True), _mock_relay_discover([]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: ""},
        )

    assert result["step_id"] == "relay_manual"

    with patch_relay_integration():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"host": "192.168.10.50", "port": 30000},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_RELAY
    assert result["data"]["host"] == "192.168.10.50"
    assert result["data"][CONF_RELAY_URL] == _RELAY_URL


async def test_relay_flow_device_no_mac_falls_back_to_manual(
    hass: HomeAssistant,
) -> None:
    """Test relay device selection falls back to manual when device has no MAC."""
    devices = [
        {
            "ip": "192.168.10.50",
            "ble_mac": None,
            "mac": None,
            "wifi_mac": None,
            "device_type": "VenusE 3.0",
            "version": 111,
        }
    ]

    result = await _init_and_select_relay(hass)

    with _mock_relay_health(reachable=True), _mock_relay_discover(devices):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_RELAY_URL: _RELAY_URL, CONF_RELAY_API_KEY: ""},
        )

    assert result["step_id"] == "relay_select"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"device": "0"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_discovery_info"}


async def test_relay_entry_setup(hass: HomeAssistant) -> None:
    """Test that a relay config entry sets up correctly with a mock relay client."""
    relay_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            "host": "192.168.10.50",
            "ble_mac": "AA:BB:CC:DD:EE:FF",
            "mac": "AA:BB:CC:DD:EE:FF",
            "device_type": "VenusE 3.0",
            "version": 111,
            "wifi_name": "marstek",
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_RELAY,
            CONF_RELAY_URL: _RELAY_URL,
        },
    )
    relay_entry.add_to_hass(hass)

    with patch_relay_integration():
        assert await hass.config_entries.async_setup(relay_entry.entry_id)
        await hass.async_block_till_done()

    assert relay_entry.state.value == "loaded"


# ---------------------------------------------------------------------------
# Direct unit tests for _discover_via_relay and _check_relay_health
# ---------------------------------------------------------------------------


async def test_discover_via_relay_success() -> None:
    """Test _discover_via_relay returns device list from relay server."""
    import aiohttp  # noqa: PLC0415

    from custom_components.marstek.config_flow import _discover_via_relay  # noqa: PLC0415

    devices = [{"ip": "1.2.3.4", "ble_mac": "aabbccddeeff"}]
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={"devices": devices})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await _discover_via_relay("http://relay:8765", None)

    assert result == devices


async def test_discover_via_relay_with_api_key() -> None:
    """Test _discover_via_relay sends API key header."""
    from custom_components.marstek.config_flow import _discover_via_relay  # noqa: PLC0415

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={"devices": []})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await _discover_via_relay("http://relay:8765", "mykey")

    call_kwargs = mock_session.post.call_args[1]
    assert call_kwargs["headers"]["X-API-Key"] == "mykey"


async def test_check_relay_health_reachable() -> None:
    """Test _check_relay_health returns True for 200 response."""
    from custom_components.marstek.config_flow import _check_relay_health  # noqa: PLC0415

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await _check_relay_health("http://relay:8765", None)

    assert result is True


async def test_check_relay_health_not_reachable() -> None:
    """Test _check_relay_health returns False on ClientError."""
    import aiohttp  # noqa: PLC0415

    from custom_components.marstek.config_flow import _check_relay_health  # noqa: PLC0415

    mock_session = MagicMock()
    mock_session.get = MagicMock(
        side_effect=aiohttp.ClientConnectionError("refused")
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await _check_relay_health("http://relay:8765", None)

    assert result is False


async def test_check_relay_health_with_api_key() -> None:
    """Test _check_relay_health sends API key header."""
    from custom_components.marstek.config_flow import _check_relay_health  # noqa: PLC0415

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await _check_relay_health("http://relay:8765", "mykey")

    call_kwargs = mock_session.get.call_args[1]
    assert call_kwargs["headers"]["X-API-Key"] == "mykey"
