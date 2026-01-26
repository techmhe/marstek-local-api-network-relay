"""Data parsing utilities for pymarstek responses."""

from __future__ import annotations

from typing import Any

_LOGGER = None


def _get_logger():
    """Lazy import logger to avoid circular imports."""
    global _LOGGER
    if _LOGGER is None:
        import logging
        _LOGGER = logging.getLogger(__name__)
    return _LOGGER


def parse_es_mode_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse ES.GetMode response into structured data.
    
    ES.GetMode returns device mode and grid power info, NOT battery power.
    For actual battery power, use parse_es_status_response with ES.GetStatus.
    
    Args:
        response: Raw response from ES.GetMode command
        
    Returns:
        Dictionary with parsed mode and grid data (device_mode, ongrid_power)
    """
    result = response.get("result", {})
    
    battery_soc = result.get("bat_soc", 0)
    ongrid_power = result.get("ongrid_power", 0)
    raw_mode = result.get("mode", "Unknown")
    # Convert API mode to lowercase HA mode
    device_mode = raw_mode.lower() if raw_mode else "unknown"
    
    # NOTE: ongrid_power is GRID power, not battery power!
    # Positive = exporting to grid, Negative = importing from grid
    
    return {
        "battery_soc": battery_soc,
        "device_mode": device_mode,
        "ongrid_power": ongrid_power,
        # Don't set battery_power here - it comes from ES.GetStatus
    }


def parse_es_status_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse ES.GetStatus response into structured data.
    
    ES.GetStatus returns actual battery power and energy statistics.
    Field names match the official Marstek Open API spec.
    
    Args:
        response: Raw response from ES.GetStatus command
        
    Returns:
        Dictionary with parsed battery data (battery_power, battery_status, etc.)
    """
    result = response.get("result", {})
    
    # ES.GetStatus fields per official API spec (docs/marstek_device_openapi.MD)
    bat_soc = result.get("bat_soc", 0)
    bat_cap = result.get("bat_cap", 0)  # Battery capacity in Wh
    pv_power = result.get("pv_power", 0)  # Solar power
    ongrid_power = result.get("ongrid_power", 0)  # Grid power
    offgrid_power = result.get("offgrid_power", 0)
    bat_power = result.get("bat_power", 0)  # Battery power (+ = discharge, - = charge)
    
    # Energy totals
    total_pv_energy = result.get("total_pv_energy", 0)
    total_grid_output_energy = result.get("total_grid_output_energy", 0)
    total_grid_input_energy = result.get("total_grid_input_energy", 0)
    total_load_energy = result.get("total_load_energy", 0)
    
    # Calculate battery_status from bat_power direction
    # Positive bat_power = discharging (selling), Negative = charging (buying)
    if bat_power > 0:
        battery_status = "Selling"
    elif bat_power < 0:
        battery_status = "Buying"
    else:
        battery_status = "Idle"
    
    return {
        "battery_soc": bat_soc,
        "battery_power": abs(bat_power),  # Expose as absolute value for display
        "battery_status": battery_status,
        "ongrid_power": ongrid_power,
        "offgrid_power": offgrid_power,
        "bat_cap": bat_cap,
        "pv_power": pv_power,
        "total_pv_energy": total_pv_energy,
        "total_grid_output_energy": total_grid_output_energy,
        "total_grid_input_energy": total_grid_input_energy,
        "total_load_energy": total_load_energy,
    }


def parse_pv_status_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse PV.GetStatus response into structured data.
    
    Note: The API spec shows single PV channel fields (pv_power, pv_voltage, pv_current).
    Some devices may return multi-channel data with prefixes (pv1_, pv2_, etc.).
    This parser handles both formats.
    
    Args:
        response: Raw response from PV.GetStatus command
        
    Returns:
        Dictionary with parsed PV channel data (pv1-pv4 or single pv_)
    """
    result = response.get("result", {})
    
    pv_data: dict[str, Any] = {}
    
    # Check for single-channel format (per API spec)
    if "pv_power" in result:
        # Single PV channel - map to pv1_* for consistency
        pv_data["pv1_power"] = result.get("pv_power", 0)
        pv_data["pv1_voltage"] = result.get("pv_voltage", 0)
        pv_data["pv1_current"] = result.get("pv_current", 0)
        pv_data["pv1_state"] = 1 if result.get("pv_power", 0) > 0 else 0
    else:
        # Multi-channel format - extract data for each PV channel (1-4)
        for channel in range(1, 5):
            prefix = f"pv{channel}_"
            pv_data[f"{prefix}power"] = result.get(f"{prefix}power", 0)
            pv_data[f"{prefix}voltage"] = result.get(f"{prefix}voltage", 0)
            pv_data[f"{prefix}current"] = result.get(f"{prefix}current", 0)
            pv_data[f"{prefix}state"] = result.get(f"{prefix}state", 0)
    
    return pv_data


def parse_wifi_status_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse Wifi.GetStatus response into structured data.
    
    Provides WiFi signal strength (RSSI) and network information.
    
    Args:
        response: Raw response from Wifi.GetStatus command
        
    Returns:
        Dictionary with WiFi data (wifi_rssi, wifi_ssid, etc.)
    """
    result = response.get("result", {})
    
    return {
        "wifi_rssi": result.get("rssi"),  # Signal strength in dBm
        "wifi_ssid": result.get("ssid"),
        "wifi_sta_ip": result.get("sta_ip"),
        "wifi_sta_gate": result.get("sta_gate"),
        "wifi_sta_mask": result.get("sta_mask"),
        "wifi_sta_dns": result.get("sta_dns"),
    }


def parse_em_status_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse EM.GetStatus (Energy Meter/CT) response into structured data.
    
    Provides CT connection state and phase power readings.
    
    Args:
        response: Raw response from EM.GetStatus command
        
    Returns:
        Dictionary with energy meter data (ct_state, phase powers, total_power)
    """
    result = response.get("result", {})
    
    ct_state_raw = result.get("ct_state")
    # Convert to boolean-friendly value: 0=Not connected, 1=Connected
    ct_connected = ct_state_raw == 1 if ct_state_raw is not None else None
    
    return {
        "ct_state": ct_state_raw,  # Raw value: 0=Not connected, 1=Connected
        "ct_connected": ct_connected,  # Boolean for binary sensor
        "em_a_power": result.get("a_power"),  # Phase A power [W]
        "em_b_power": result.get("b_power"),  # Phase B power [W]
        "em_c_power": result.get("c_power"),  # Phase C power [W]
        "em_total_power": result.get("total_power"),  # Total grid power [W]
    }


def parse_bat_status_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse Bat.GetStatus response into structured data.
    
    Provides detailed battery information including temperature and capacity.
    
    Args:
        response: Raw response from Bat.GetStatus command
        
    Returns:
        Dictionary with battery data (bat_temp, charge flags, capacity)
    """
    result = response.get("result", {})
    
    return {
        "bat_temp": result.get("bat_temp"),  # Battery temperature [°C]
        "bat_charg_flag": result.get("charg_flag"),  # Charging permission flag
        "bat_dischrg_flag": result.get("dischrg_flag"),  # Discharge permission flag
        "bat_capacity": result.get("bat_capacity"),  # Remaining capacity [Wh]
        "bat_rated_capacity": result.get("rated_capacity"),  # Rated capacity [Wh]
        "bat_soc_detailed": result.get("soc"),  # SOC from Bat.GetStatus
    }


def merge_device_status(
    es_mode_data: dict[str, Any] | None = None,
    es_status_data: dict[str, Any] | None = None,
    pv_status_data: dict[str, Any] | None = None,
    wifi_status_data: dict[str, Any] | None = None,
    em_status_data: dict[str, Any] | None = None,
    bat_status_data: dict[str, Any] | None = None,
    device_ip: str | None = None,
    last_update: float | None = None,
) -> dict[str, Any]:
    """Merge all status data into a complete device status.
    
    Priority order for overlapping keys:
    1. es_status_data (most accurate for battery_power, battery_status)
    2. es_mode_data (device_mode, ongrid_power)
    3. bat_status_data (battery temperature, capacity details)
    4. wifi_status_data (WiFi RSSI, network info)
    5. em_status_data (CT connection, phase powers)
    6. pv_status_data (PV channel data)
    
    Args:
        es_mode_data: Parsed ES.GetMode data (device_mode, ongrid_power)
        es_status_data: Parsed ES.GetStatus data (battery_power, battery_status)
        pv_status_data: Parsed PV.GetStatus data
        wifi_status_data: Parsed Wifi.GetStatus data (rssi, network info)
        em_status_data: Parsed EM.GetStatus data (CT state, phase powers)
        bat_status_data: Parsed Bat.GetStatus data (temperature, capacity)
        device_ip: Device IP address
        last_update: Timestamp of last update
        
    Returns:
        Complete device status dictionary
    """
    status: dict[str, Any] = {
        "battery_soc": 0,
        "battery_power": 0,
        "device_mode": "Unknown",
        "battery_status": "Unknown",
        "ongrid_power": 0,
        "household_consumption": 0,
        "pv1_power": 0,
        "pv1_voltage": 0,
        "pv1_current": 0,
        "pv1_state": 0,
        "pv2_power": 0,
        "pv2_voltage": 0,
        "pv2_current": 0,
        "pv2_state": 0,
        "pv3_power": 0,
        "pv3_voltage": 0,
        "pv3_current": 0,
        "pv3_state": 0,
        "pv4_power": 0,
        "pv4_voltage": 0,
        "pv4_current": 0,
        "pv4_state": 0,
        # WiFi status defaults
        "wifi_rssi": None,
        "wifi_ssid": None,
        # Energy meter / CT defaults
        "ct_state": None,
        "ct_connected": None,
        "em_a_power": None,
        "em_b_power": None,
        "em_c_power": None,
        "em_total_power": None,
        # Battery details defaults
        "bat_temp": None,
        "bat_charg_flag": None,
        "bat_dischrg_flag": None,
    }
    
    # Apply in order of priority (lowest to highest)
    if pv_status_data:
        status.update(pv_status_data)
    
    if em_status_data:
        status.update(em_status_data)
    
    if wifi_status_data:
        status.update(wifi_status_data)
    
    if bat_status_data:
        status.update(bat_status_data)
    
    if es_mode_data:
        status.update(es_mode_data)
    
    # ES.GetStatus has highest priority for battery data
    if es_status_data:
        status.update(es_status_data)
    
    if device_ip:
        status["device_ip"] = device_ip
    
    if last_update is not None:
        status["last_update"] = last_update
    
    return status

