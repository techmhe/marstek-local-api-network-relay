"""Tests for Marstek diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.marstek import MarstekConfigEntry
from custom_components.marstek.diagnostics import async_get_config_entry_diagnostics


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create a mock config entry."""
    entry = MagicMock(spec=MarstekConfigEntry)
    entry.title = "Test Marstek Device"
    entry.data = {
        "host": "192.168.1.100",
        "mac": "AA:BB:CC:DD:EE:FF",
        "ble_mac": "11:22:33:44:55:66",
        "wifi_mac": "77:88:99:AA:BB:CC",
        "wifi_name": "TestNetwork",
        "device_type": "Venus",
        "version": 1,
    }
    entry.options = {"poll_interval_fast": 30}
    return entry


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {
        "battery_level": 75,
        "grid_power": 500,
        "device_mode": "Auto",
        "ip": "192.168.1.100",
        "bleMac": "11:22:33:44:55:66",
        "SSID": "TestNetwork",
    }
    coordinator.last_update_success = True
    coordinator.last_exception = None
    return coordinator


@pytest.fixture
def mock_runtime_data(mock_coordinator: MagicMock) -> MagicMock:
    """Create mock runtime data."""
    runtime_data = MagicMock()
    runtime_data.coordinator = mock_coordinator
    runtime_data.device_info = {
        "ip": "192.168.1.100",
        "mac": "AA:BB:CC:DD:EE:FF",
        "ble_mac": "11:22:33:44:55:66",
        "wifi_mac": "77:88:99:AA:BB:CC",
        "wifi_name": "TestNetwork",
        "device_type": "Venus",
        "version": 1,
    }
    return runtime_data


async def test_async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MagicMock,
    mock_runtime_data: MagicMock,
) -> None:
    """Test diagnostics returns correct structure."""
    mock_config_entry.runtime_data = mock_runtime_data

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Verify structure
    assert "entry" in result
    assert "device_info" in result
    assert "coordinator_data" in result
    assert "last_update_success" in result
    assert "last_exception" in result

    # Verify entry data
    assert result["entry"]["title"] == "Test Marstek Device"
    assert result["last_update_success"] is True
    assert result["last_exception"] is None


async def test_diagnostics_redacts_sensitive_data(
    hass: HomeAssistant,
    mock_config_entry: MagicMock,
    mock_runtime_data: MagicMock,
) -> None:
    """Test that sensitive data is redacted."""
    mock_config_entry.runtime_data = mock_runtime_data

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Check that sensitive fields are redacted in entry data
    entry_data = result["entry"]["data"]
    assert entry_data.get("host") == "**REDACTED**"
    assert entry_data.get("mac") == "**REDACTED**"
    assert entry_data.get("ble_mac") == "**REDACTED**"
    assert entry_data.get("wifi_mac") == "**REDACTED**"
    assert entry_data.get("wifi_name") == "**REDACTED**"

    # Check that sensitive fields are redacted in device_info
    device_info = result["device_info"]
    assert device_info.get("ip") == "**REDACTED**"
    assert device_info.get("mac") == "**REDACTED**"
    assert device_info.get("ble_mac") == "**REDACTED**"

    # Check that sensitive fields are redacted in coordinator_data
    coordinator_data = result["coordinator_data"]
    assert coordinator_data.get("ip") == "**REDACTED**"
    assert coordinator_data.get("bleMac") == "**REDACTED**"
    assert coordinator_data.get("SSID") == "**REDACTED**"


async def test_diagnostics_with_exception(
    hass: HomeAssistant,
    mock_config_entry: MagicMock,
    mock_runtime_data: MagicMock,
) -> None:
    """Test diagnostics when coordinator has an exception."""
    mock_runtime_data.coordinator.last_update_success = False
    mock_runtime_data.coordinator.last_exception = TimeoutError("Connection timeout")
    mock_config_entry.runtime_data = mock_runtime_data

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["last_update_success"] is False
    assert "Connection timeout" in result["last_exception"]


async def test_diagnostics_with_empty_coordinator_data(
    hass: HomeAssistant,
    mock_config_entry: MagicMock,
    mock_runtime_data: MagicMock,
) -> None:
    """Test diagnostics when coordinator has no data."""
    mock_runtime_data.coordinator.data = None
    mock_config_entry.runtime_data = mock_runtime_data

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["coordinator_data"] == {}
