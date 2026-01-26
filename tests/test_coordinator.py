"""Tests for Marstek coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.marstek.const import DOMAIN
from custom_components.marstek.coordinator import MarstekDataUpdateCoordinator


@pytest.fixture
def mock_udp_client():
    """Create a mock UDP client."""
    client = MagicMock()
    client.is_polling_paused = MagicMock(return_value=False)
    client.get_device_status = AsyncMock(
        return_value={
            "battery_soc": 55,
            "battery_power": 100,
            "device_mode": "auto",
            "battery_status": "Charging",
            "pv1_power": 200,
        }
    )
    return client


async def test_coordinator_init(hass: HomeAssistant, mock_config_entry, mock_udp_client):
    """Test coordinator initialization."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    assert coordinator.device_ip == "1.2.3.4"
    assert coordinator.udp_client is mock_udp_client
    assert coordinator.config_entry is mock_config_entry
    assert coordinator.name == "Marstek 1.2.3.4"


async def test_coordinator_device_ip_from_config_entry(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test device_ip reads from config entry dynamically."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    # Initial IP should match
    assert coordinator.device_ip == "1.2.3.4"


async def test_coordinator_successful_update(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test successful data update."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    data = await coordinator._async_update_data()

    assert data["battery_soc"] == 55
    assert data["battery_power"] == 100
    assert data["device_mode"] == "auto"
    mock_udp_client.get_device_status.assert_called_once()


async def test_coordinator_polling_paused_returns_cached_data(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test that polling paused returns cached data."""
    mock_config_entry.add_to_hass(hass)
    mock_udp_client.is_polling_paused = MagicMock(return_value=True)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )
    # Set some cached data
    coordinator.data = {"cached": "data"}

    data = await coordinator._async_update_data()

    # Should return cached data without calling get_device_status
    assert data == {"cached": "data"}
    mock_udp_client.get_device_status.assert_not_called()


async def test_coordinator_polling_paused_returns_empty_dict_when_no_cache(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test that polling paused returns empty dict when no cached data."""
    mock_config_entry.add_to_hass(hass)
    mock_udp_client.is_polling_paused = MagicMock(return_value=True)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )
    # No cached data
    coordinator.data = None

    data = await coordinator._async_update_data()

    assert data == {}
    mock_udp_client.get_device_status.assert_not_called()


async def test_coordinator_invalid_data_raises_update_failed(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test that invalid data (device_mode=Unknown) raises UpdateFailed."""
    mock_config_entry.add_to_hass(hass)
    mock_udp_client.get_device_status = AsyncMock(
        return_value={
            "battery_soc": 0,
            "battery_power": 0,
            "device_mode": "Unknown",  # Default value indicates failure
        }
    )

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    with pytest.raises(UpdateFailed, match="Polling failed"):
        await coordinator._async_update_data()


async def test_coordinator_timeout_error_raises_update_failed(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test that TimeoutError raises UpdateFailed."""
    mock_config_entry.add_to_hass(hass)
    mock_udp_client.get_device_status = AsyncMock(side_effect=TimeoutError("timeout"))

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    with pytest.raises(UpdateFailed, match="Polling failed"):
        await coordinator._async_update_data()


async def test_coordinator_os_error_raises_update_failed(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test that OSError raises UpdateFailed."""
    mock_config_entry.add_to_hass(hass)
    mock_udp_client.get_device_status = AsyncMock(
        side_effect=OSError("Network unreachable")
    )

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    with pytest.raises(UpdateFailed, match="Polling failed"):
        await coordinator._async_update_data()


async def test_coordinator_value_error_raises_update_failed(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test that ValueError raises UpdateFailed."""
    mock_config_entry.add_to_hass(hass)
    mock_udp_client.get_device_status = AsyncMock(side_effect=ValueError("Invalid data"))

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    with pytest.raises(UpdateFailed, match="Polling failed"):
        await coordinator._async_update_data()


async def test_coordinator_config_entry_updated_ip_unchanged(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test config entry update listener when IP is unchanged."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    # Call the update listener with same config entry (same IP)
    with patch.object(
        coordinator, "_update_entity_names", new_callable=AsyncMock
    ) as mock_update:
        await coordinator._async_config_entry_updated(hass, mock_config_entry)
        mock_update.assert_not_called()


async def test_coordinator_config_entry_updated_ip_changed(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test config entry update listener when IP changes."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",  # Initial IP
    )

    # Create a new entry with changed IP
    updated_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            "host": "5.6.7.8",  # Changed IP
            "ble_mac": "AA:BB:CC:DD:EE:FF",
        },
    )

    with patch.object(
        coordinator, "_update_entity_names", new_callable=AsyncMock
    ) as mock_update:
        await coordinator._async_config_entry_updated(hass, updated_entry)
        mock_update.assert_called_once_with("5.6.7.8", "1.2.3.4")
        # Initial IP should be updated
        assert coordinator._initial_device_ip == "5.6.7.8"


async def test_coordinator_config_entry_updated_no_config_entry(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test config entry update listener when config_entry is None."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )
    # Simulate config_entry being None
    coordinator.config_entry = None

    # Should return early without error
    await coordinator._async_config_entry_updated(hass, mock_config_entry)


async def test_coordinator_update_entity_names(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test updating entity names when IP changes."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    # Mock device and entity registries
    mock_device = MagicMock()
    mock_device.name = "Marstek Venus v3 (1.2.3.4)"
    mock_device.id = "device_123"

    mock_entity = MagicMock()
    mock_entity.entity_id = "sensor.test"
    mock_entity.name = "Test Sensor (1.2.3.4)"

    with (
        patch(
            "custom_components.marstek.coordinator.dr.async_get"
        ) as mock_dr,
        patch(
            "custom_components.marstek.coordinator.er.async_get"
        ) as mock_er,
        patch(
            "custom_components.marstek.coordinator.er.async_entries_for_config_entry"
        ) as mock_entries,
    ):
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = mock_device
        mock_dr.return_value = mock_device_registry

        mock_entity_registry = MagicMock()
        mock_er.return_value = mock_entity_registry
        mock_entries.return_value = [mock_entity]

        await coordinator._update_entity_names("5.6.7.8", "1.2.3.4")

        # Device name should be updated
        mock_device_registry.async_update_device.assert_called_once_with(
            "device_123", name="Marstek Venus v3 (5.6.7.8)"
        )
        # Entity name should be updated
        mock_entity_registry.async_update_entity.assert_called_once_with(
            "sensor.test", name="Test Sensor (5.6.7.8)"
        )


async def test_coordinator_update_entity_names_no_ip_in_names(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test updating entity names when names don't contain old IP."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    # Mock device and entity registries with names that don't have IP
    mock_device = MagicMock()
    mock_device.name = "Marstek Venus v3"  # No IP in name
    mock_device.id = "device_123"

    mock_entity = MagicMock()
    mock_entity.entity_id = "sensor.test"
    mock_entity.name = "Test Sensor"  # No IP in name

    with (
        patch(
            "custom_components.marstek.coordinator.dr.async_get"
        ) as mock_dr,
        patch(
            "custom_components.marstek.coordinator.er.async_get"
        ) as mock_er,
        patch(
            "custom_components.marstek.coordinator.er.async_entries_for_config_entry"
        ) as mock_entries,
    ):
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = mock_device
        mock_dr.return_value = mock_device_registry

        mock_entity_registry = MagicMock()
        mock_er.return_value = mock_entity_registry
        mock_entries.return_value = [mock_entity]

        await coordinator._update_entity_names("5.6.7.8", "1.2.3.4")

        # Device name should NOT be updated (no IP in name)
        mock_device_registry.async_update_device.assert_not_called()
        # Entity name should NOT be updated (no IP in name)
        mock_entity_registry.async_update_entity.assert_not_called()


async def test_coordinator_update_entity_names_no_device_found(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test updating entity names when no device is found."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )

    with (
        patch(
            "custom_components.marstek.coordinator.dr.async_get"
        ) as mock_dr,
        patch(
            "custom_components.marstek.coordinator.er.async_get"
        ) as mock_er,
        patch(
            "custom_components.marstek.coordinator.er.async_entries_for_config_entry"
        ) as mock_entries,
    ):
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = None  # No device found
        mock_dr.return_value = mock_device_registry

        mock_entity_registry = MagicMock()
        mock_er.return_value = mock_entity_registry
        mock_entries.return_value = []

        # Should not raise - just skip device update
        await coordinator._update_entity_names("5.6.7.8", "1.2.3.4")

        mock_device_registry.async_update_device.assert_not_called()


async def test_coordinator_update_entity_names_no_config_entry(
    hass: HomeAssistant, mock_config_entry, mock_udp_client
):
    """Test updating entity names when config_entry is None."""
    mock_config_entry.add_to_hass(hass)

    coordinator = MarstekDataUpdateCoordinator(
        hass,
        mock_config_entry,
        mock_udp_client,
        "1.2.3.4",
    )
    coordinator.config_entry = None

    # Should return early without error
    await coordinator._update_entity_names("5.6.7.8", "1.2.3.4")
