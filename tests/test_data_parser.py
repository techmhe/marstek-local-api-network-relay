"""Tests for Marstek data parser functions."""

from __future__ import annotations

import pytest

from custom_components.marstek.pymarstek.data_parser import (
    merge_device_status,
    parse_bat_status_response,
    parse_em_status_response,
    parse_es_mode_response,
    parse_es_status_response,
    parse_pv_status_response,
    parse_wifi_status_response,
)


class TestParseWifiStatusResponse:
    """Tests for parse_wifi_status_response."""

    def test_parse_full_response(self):
        """Test parsing a complete WiFi status response."""
        response = {
            "id": 1,
            "result": {
                "rssi": -58,
                "ssid": "TestNetwork",
                "sta_ip": "192.168.1.100",
                "sta_gate": "192.168.1.1",
                "sta_mask": "255.255.255.0",
                "sta_dns": "192.168.1.1",
            },
        }

        result = parse_wifi_status_response(response)

        assert result["wifi_rssi"] == -58
        assert result["wifi_ssid"] == "TestNetwork"
        assert result["wifi_sta_ip"] == "192.168.1.100"
        assert result["wifi_sta_gate"] == "192.168.1.1"
        assert result["wifi_sta_mask"] == "255.255.255.0"
        assert result["wifi_sta_dns"] == "192.168.1.1"

    def test_parse_empty_response(self):
        """Test parsing an empty response."""
        response = {"id": 1, "result": {}}

        result = parse_wifi_status_response(response)

        assert result["wifi_rssi"] is None
        assert result["wifi_ssid"] is None

    def test_parse_partial_response(self):
        """Test parsing a partial response with only RSSI."""
        response = {
            "id": 1,
            "result": {
                "rssi": -72,
            },
        }

        result = parse_wifi_status_response(response)

        assert result["wifi_rssi"] == -72
        assert result["wifi_ssid"] is None


class TestParseEmStatusResponse:
    """Tests for parse_em_status_response (Energy Meter / CT)."""

    def test_parse_connected_ct(self):
        """Test parsing EM status with connected CT."""
        response = {
            "id": 1,
            "result": {
                "ct_state": 1,
                "a_power": 120,
                "b_power": 115,
                "c_power": 125,
                "total_power": 360,
            },
        }

        result = parse_em_status_response(response)

        assert result["ct_state"] == 1
        assert result["ct_connected"] is True
        assert result["em_a_power"] == 120
        assert result["em_b_power"] == 115
        assert result["em_c_power"] == 125
        assert result["em_total_power"] == 360

    def test_parse_disconnected_ct(self):
        """Test parsing EM status with disconnected CT."""
        response = {
            "id": 1,
            "result": {
                "ct_state": 0,
                "total_power": 0,
            },
        }

        result = parse_em_status_response(response)

        assert result["ct_state"] == 0
        assert result["ct_connected"] is False
        assert result["em_total_power"] == 0

    def test_parse_empty_response(self):
        """Test parsing empty EM response."""
        response = {"id": 1, "result": {}}

        result = parse_em_status_response(response)

        assert result["ct_state"] is None
        assert result["ct_connected"] is None
        assert result["em_a_power"] is None
        assert result["em_total_power"] is None


class TestParseBatStatusResponse:
    """Tests for parse_bat_status_response."""

    def test_parse_full_response(self):
        """Test parsing a complete battery status response."""
        response = {
            "id": 1,
            "result": {
                "bat_temp": 27.5,
                "charg_flag": 1,
                "dischrg_flag": 1,
                "bat_capacity": 2560,
                "rated_capacity": 5120,
                "soc": 50,
            },
        }

        result = parse_bat_status_response(response)

        assert result["bat_temp"] == 27.5
        assert result["bat_charg_flag"] == 1
        assert result["bat_dischrg_flag"] == 1
        assert result["bat_capacity"] == 2560
        assert result["bat_rated_capacity"] == 5120
        assert result["bat_soc_detailed"] == 50

    def test_parse_empty_response(self):
        """Test parsing empty battery response returns None values."""
        response = {"id": 1, "result": {}}

        result = parse_bat_status_response(response)

        assert result["bat_temp"] is None
        assert result["bat_charg_flag"] is None
        assert result["bat_dischrg_flag"] is None

    def test_parse_charging_disabled(self):
        """Test parsing battery with charging disabled."""
        response = {
            "id": 1,
            "result": {
                "bat_temp": 45.0,  # High temp may disable charging
                "charg_flag": 0,
                "dischrg_flag": 1,
                "soc": 95,
            },
        }

        result = parse_bat_status_response(response)

        assert result["bat_temp"] == 45.0
        assert result["bat_charg_flag"] == 0
        assert result["bat_dischrg_flag"] == 1


class TestParsePvStatusResponse:
    """Tests for parse_pv_status_response."""

    def test_parse_multi_channel_format(self):
        """Test parsing multi-channel PV response (pv1_, pv2_, etc.)."""
        response = {
            "id": 1,
            "result": {
                "pv1_power": 300,
                "pv1_voltage": 35,
                "pv1_current": 8.5,
                "pv1_state": 1,
                "pv2_power": 250,
                "pv2_voltage": 34,
                "pv2_current": 7.3,
                "pv2_state": 1,
            },
        }

        result = parse_pv_status_response(response)

        assert result["pv1_power"] == 300
        assert result["pv1_voltage"] == 35
        assert result["pv1_current"] == 8.5
        assert result["pv1_state"] == 1
        assert result["pv2_power"] == 250

    def test_parse_single_channel_format(self):
        """Test parsing single-channel PV response (pv_ without number)."""
        response = {
            "id": 1,
            "result": {
                "pv_power": 500,
                "pv_voltage": 36,
                "pv_current": 13.8,
            },
        }

        result = parse_pv_status_response(response)

        # Should be mapped to pv1_* for consistency
        assert result["pv1_power"] == 500
        assert result["pv1_voltage"] == 36
        assert result["pv1_current"] == 13.8
        assert result["pv1_state"] == 1  # Active since power > 0

    def test_parse_single_channel_no_power(self):
        """Test single-channel format with zero power sets state to 0."""
        response = {
            "id": 1,
            "result": {
                "pv_power": 0,
                "pv_voltage": 0,
                "pv_current": 0,
            },
        }

        result = parse_pv_status_response(response)

        assert result["pv1_power"] == 0
        assert result["pv1_state"] == 0  # Inactive since power = 0


class TestMergeDeviceStatus:
    """Tests for merge_device_status."""

    def test_merge_all_data_sources(self):
        """Test merging data from all API sources."""
        es_mode_data = {
            "device_mode": "auto",
            "ongrid_power": 150,
            "battery_soc": 55,
        }
        es_status_data = {
            "battery_soc": 55,
            "battery_power": 250,
            "battery_status": "Selling",
        }
        pv_status_data = {
            "pv1_power": 300,
            "pv1_voltage": 35,
        }
        wifi_status_data = {
            "wifi_rssi": -58,
            "wifi_ssid": "TestNetwork",
        }
        em_status_data = {
            "ct_state": 1,
            "ct_connected": True,
            "em_total_power": 360,
        }
        bat_status_data = {
            "bat_temp": 27.5,
            "bat_charg_flag": 1,
        }

        result = merge_device_status(
            es_mode_data=es_mode_data,
            es_status_data=es_status_data,
            pv_status_data=pv_status_data,
            wifi_status_data=wifi_status_data,
            em_status_data=em_status_data,
            bat_status_data=bat_status_data,
            device_ip="192.168.1.100",
            last_update=1234567890.0,
        )

        # Check all merged fields
        assert result["device_mode"] == "auto"
        assert result["battery_soc"] == 55
        assert result["battery_power"] == 250
        assert result["battery_status"] == "Selling"
        assert result["pv1_power"] == 300
        assert result["wifi_rssi"] == -58
        assert result["ct_connected"] is True
        assert result["em_total_power"] == 360
        assert result["bat_temp"] == 27.5
        assert result["device_ip"] == "192.168.1.100"
        assert result["last_update"] == 1234567890.0

    def test_merge_with_none_data_sources(self):
        """Test merging when some data sources are None."""
        es_mode_data = {
            "device_mode": "auto",
            "ongrid_power": 150,
        }

        result = merge_device_status(
            es_mode_data=es_mode_data,
            es_status_data=None,
            pv_status_data=None,
            wifi_status_data=None,
            em_status_data=None,
            bat_status_data=None,
        )

        # Should have defaults for missing data
        assert result["device_mode"] == "auto"
        assert result["battery_soc"] == 0  # Default
        assert result["wifi_rssi"] is None  # Default for optional field
        assert result["ct_connected"] is None  # Default for optional field
        assert result["bat_temp"] is None  # Default for optional field

    def test_es_status_priority_over_es_mode(self):
        """Test that ES.GetStatus battery_soc takes priority over ES.GetMode."""
        es_mode_data = {
            "battery_soc": 50,  # Lower priority
        }
        es_status_data = {
            "battery_soc": 55,  # Higher priority
        }

        result = merge_device_status(
            es_mode_data=es_mode_data,
            es_status_data=es_status_data,
        )

        # ES.GetStatus should win
        assert result["battery_soc"] == 55


class TestParseEsModeResponse:
    """Tests for parse_es_mode_response."""

    def test_parse_auto_mode(self):
        """Test parsing Auto mode response."""
        response = {
            "id": 1,
            "result": {
                "mode": "Auto",
                "bat_soc": 55,
                "ongrid_power": -150,
            },
        }

        result = parse_es_mode_response(response)

        assert result["device_mode"] == "auto"
        assert result["battery_soc"] == 55
        assert result["ongrid_power"] == -150


class TestParseEsStatusResponse:
    """Tests for parse_es_status_response."""

    def test_parse_charging_status(self):
        """Test parsing charging battery status."""
        response = {
            "id": 1,
            "result": {
                "bat_soc": 55,
                "bat_cap": 5120,
                "bat_power": -1000,  # Negative = charging
                "pv_power": 1200,
                "ongrid_power": 200,
            },
        }

        result = parse_es_status_response(response)

        assert result["battery_soc"] == 55
        assert result["battery_power"] == 1000  # abs() applied
        assert result["battery_status"] == "Buying"  # Charging = Buying

    def test_parse_discharging_status(self):
        """Test parsing discharging battery status."""
        response = {
            "id": 1,
            "result": {
                "bat_soc": 55,
                "bat_power": 800,  # Positive = discharging
                "ongrid_power": -500,
            },
        }

        result = parse_es_status_response(response)

        assert result["battery_power"] == 800
        assert result["battery_status"] == "Selling"  # Discharging = Selling

    def test_parse_idle_status(self):
        """Test parsing idle battery status."""
        response = {
            "id": 1,
            "result": {
                "bat_soc": 55,
                "bat_power": 0,  # Zero = idle
            },
        }

        result = parse_es_status_response(response)

        assert result["battery_power"] == 0
        assert result["battery_status"] == "Idle"
