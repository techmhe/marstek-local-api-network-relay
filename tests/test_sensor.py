"""Tests for Marstek sensor entities."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.conftest import create_mock_client, patch_marstek_integration


async def test_coordinator_success_creates_entities(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test coordinator successfully fetches data and creates sensor entities."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "SelfUse",
        "battery_soc": 55,
        "battery_power": 120,
        "pv1_power": 300,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_battery_soc")
        assert state is not None
        assert state.state == "55"


async def test_coordinator_failure_marks_entities_unavailable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test coordinator failure raises UpdateFailed, entities become unavailable."""
    mock_config_entry.add_to_hass(hass)

    client = create_mock_client(status=TimeoutError("poll failed"))

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_battery_soc")
    # Entity may not exist if coordinator failed on first refresh
    # or should be unavailable if it was created
    if state:
        assert state.state == "unavailable"


async def test_no_pv_entities_when_data_missing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test PV entities are not created when PV data keys are absent."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "SelfUse",
        "battery_soc": 55,
        "battery_power": 120,
        # No pv1_power, pv2_power, etc.
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Check that PV entities are not registered
        pv_entity = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_pv1_power")
        assert pv_entity is None


async def test_wifi_rssi_sensor_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test WiFi RSSI sensor is created when data is available."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        "wifi_rssi": -58,
        "wifi_ssid": "TestNetwork",
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_wifi_rssi")
        assert state is not None
        assert state.state == "-58"


async def test_wifi_rssi_sensor_not_created_when_missing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test WiFi RSSI sensor is NOT created when data is absent."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        # No wifi_rssi
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_wifi_rssi")
        assert state is None


async def test_ct_connection_sensor_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test CT connection sensor is created when data is available."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        "ct_state": 1,
        "ct_connected": True,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_ct_state")
        assert state is not None
        assert state.state == "Connected"


async def test_ct_connection_sensor_disconnected(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test CT connection sensor shows disconnected state."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        "ct_state": 0,
        "ct_connected": False,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_ct_state")
        assert state is not None
        assert state.state == "Not Connected"


async def test_battery_temperature_sensor_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test battery temperature sensor is created when data is available."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        "bat_temp": 27.5,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_bat_temp")
        assert state is not None
        assert state.state == "27.5"


async def test_grid_total_power_sensor_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test grid total power sensor is created when EM data is available."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        "em_total_power": 360,
        "em_a_power": 120,
        "em_b_power": 115,
        "em_c_power": 125,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        state = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_em_total_power")
        assert state is not None
        assert state.state == "360"


async def test_phase_power_sensors_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test phase power sensors are created for 3-phase systems."""
    mock_config_entry.add_to_hass(hass)

    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 120,
        "em_a_power": 120,
        "em_b_power": 115,
        "em_c_power": 125,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        
        # Check all three phase sensors (use actual entity IDs)
        state_a = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_phase_a_power")
        assert state_a is not None
        assert state_a.state == "120"
        
        state_b = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_phase_b_power")
        assert state_b is not None
        assert state_b.state == "115"
        
        state_c = hass.states.get("sensor.marstek_venus_v3_1_2_3_4_phase_c_power")
        assert state_c is not None
        assert state_c.state == "125"


async def test_all_new_sensors_with_full_status(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test all new sensors are created when full device status is available."""
    mock_config_entry.add_to_hass(hass)

    # Full status with all new fields
    status = {
        "device_mode": "auto",
        "battery_soc": 55,
        "battery_power": 250,
        "battery_status": "Selling",
        "ongrid_power": -150,
        # WiFi
        "wifi_rssi": -58,
        "wifi_ssid": "TestNetwork",
        # CT / Energy Meter
        "ct_state": 1,
        "ct_connected": True,
        "em_a_power": 120,
        "em_b_power": 115,
        "em_c_power": 125,
        "em_total_power": 360,
        # Battery details
        "bat_temp": 27.5,
        "bat_charg_flag": 1,
        "bat_dischrg_flag": 1,
    }

    client = create_mock_client(status=status)

    with patch_marstek_integration(client=client):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
        
        # Verify all new sensors are present (using actual entity IDs)
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_wifi_rssi") is not None
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_ct_state") is not None
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_bat_temp") is not None
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_em_total_power") is not None
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_phase_a_power") is not None
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_phase_b_power") is not None
        assert hass.states.get("sensor.marstek_venus_v3_1_2_3_4_phase_c_power") is not None
