"""Diagnostics support for Marstek integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import MarstekConfigEntry

TO_REDACT = {
    CONF_HOST,
    "ip",
    "mac",
    "wifi_mac",
    "ble_mac",
    "wifi_name",
    "unique_id",
    "wifiMac",
    "bleMac",
    "SSID",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MarstekConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    device_info = entry.runtime_data.device_info

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "device_info": async_redact_data(device_info, TO_REDACT),
        "coordinator_data": async_redact_data(
            coordinator.data if coordinator.data else {}, TO_REDACT
        ),
        "last_update_success": coordinator.last_update_success,
        "last_exception": str(coordinator.last_exception)
        if coordinator.last_exception
        else None,
    }
