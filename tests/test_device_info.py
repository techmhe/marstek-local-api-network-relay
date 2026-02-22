"""Tests for device info and binary sensor edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.marstek.binary_sensor import MarstekBinarySensor
from custom_components.marstek.helpers.binary_sensor_descriptions import BINARY_SENSORS
from custom_components.marstek.device_info import build_device_info, get_device_identifier


def test_get_device_identifier_requires_mac() -> None:
    """Missing MAC data AND no fallback should raise a ValueError."""
    with pytest.raises(ValueError, match="identifier"):
        get_device_identifier({})


def test_get_device_identifier_falls_back_to_entry_id() -> None:
    """entry_id is used as identifier when no MAC is present (relay-manual entries)."""
    result = get_device_identifier({"entry_id": "abc-123-def"})
    assert result == "abc-123-def"


def test_get_device_identifier_prefers_mac_over_entry_id() -> None:
    """MAC takes priority over entry_id when both are present."""
    result = get_device_identifier(
        {"ble_mac": "AA:BB:CC:DD:EE:FF", "entry_id": "abc-123-def"}
    )
    assert result == "aa:bb:cc:dd:ee:ff"


def test_binary_sensor_returns_none_when_no_data() -> None:
    """Binary sensor should return None when coordinator has no data."""
    coordinator = MagicMock()
    coordinator.data = None
    coordinator.async_add_listener.return_value = lambda: None

    device_info = {"ble_mac": "AA:BB:CC:DD:EE:FF", "device_type": "Venus"}
    description = BINARY_SENSORS[0]

    entity = MarstekBinarySensor(coordinator, device_info, description)

    assert entity.is_on is None


def test_build_device_info_formats_device_name() -> None:
    """Device name should be short and exclude firmware version."""
    device_info = {
        "ble_mac": "AA:BB:CC:DD:EE:FF",
        "device_type": "VenusA 3.0",
        "version": 147,
    }

    device = build_device_info(device_info)

    assert device["name"] == "Venus A (3.0)"
    assert device["manufacturer"] == "Marstek"
    assert device["sw_version"] == "147"
