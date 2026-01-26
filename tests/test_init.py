"""Tests for Marstek integration setup/unload lifecycle."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.marstek.const import DOMAIN

from tests.conftest import create_mock_client, patch_marstek_integration


async def test_setup_and_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test setup creates coordinator, platforms, and successful unload."""
    mock_config_entry.add_to_hass(hass)

    client = create_mock_client(
        status={
            "device_mode": "SelfUse",
            "battery_soc": 55,
            "battery_power": 120,
        }
    )

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_battery_soc") is not None

        # Unload
        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state == ConfigEntryState.NOT_LOADED
    assert DOMAIN not in hass.data


async def test_setup_connection_failure_triggers_retry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test setup raises ConfigEntryNotReady on connection failure."""
    mock_config_entry.add_to_hass(hass)

    # Simulate timeout during initial connectivity check (send_request fails)
    client = create_mock_client(send_request_error=TimeoutError("timeout"))

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # ConfigEntryNotReady results in SETUP_RETRY, not SETUP_ERROR
    assert mock_config_entry.state == ConfigEntryState.SETUP_RETRY


async def test_reload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test reloading the integration re-establishes coordinator."""
    mock_config_entry.add_to_hass(hass)

    client = create_mock_client(
        status={
            "device_mode": "auto",
            "battery_soc": 75,
        }
    )

    with patch_marstek_integration(client=client):
        # Initial setup
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert mock_config_entry.state == ConfigEntryState.LOADED

        # Reload
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_battery_soc") is not None


async def test_services_registered_during_setup(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that domain services are registered during async_setup."""
    mock_config_entry.add_to_hass(hass)

    client = create_mock_client()

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Verify services are registered
    assert hass.services.has_service(DOMAIN, "set_passive_mode")
    assert hass.services.has_service(DOMAIN, "set_manual_schedule")
    assert hass.services.has_service(DOMAIN, "clear_manual_schedules")
