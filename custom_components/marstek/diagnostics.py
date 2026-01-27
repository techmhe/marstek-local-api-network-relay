"""Diagnostics support for Marstek integration."""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import MarstekConfigEntry
from .const import (
    CONF_POLL_INTERVAL_FAST,
    CONF_POLL_INTERVAL_MEDIUM,
    CONF_POLL_INTERVAL_SLOW,
    CONF_REQUEST_DELAY,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_POLL_INTERVAL_FAST,
    DEFAULT_POLL_INTERVAL_MEDIUM,
    DEFAULT_POLL_INTERVAL_SLOW,
    DEFAULT_REQUEST_DELAY,
    DEFAULT_REQUEST_TIMEOUT,
)

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


def _format_exception(exc: BaseException | None) -> dict[str, Any] | None:
    """Format exception with full traceback for diagnostics."""
    if exc is None:
        return None

    result: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
    }

    # Include the original cause if this is a chained exception
    if exc.__cause__ is not None:
        result["cause"] = {
            "type": type(exc.__cause__).__name__,
            "message": str(exc.__cause__),
            "traceback": traceback.format_exception(
                type(exc.__cause__), exc.__cause__, exc.__cause__.__traceback__
            ),
        }

    return result


def _format_datetime(dt: datetime | None) -> str | None:
    """Format datetime as ISO string with timezone."""
    if dt is None:
        return None
    return dt.isoformat()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MarstekConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    device_info = entry.runtime_data.device_info

    # Get current time for reference
    now = dt_util.now()

    # Calculate time since last successful update
    last_success_time = getattr(coordinator, "last_update_success_time", None)
    time_since_success = None
    if last_success_time is not None:
        delta = now - last_success_time
        time_since_success = f"{delta.total_seconds():.1f} seconds ago"

    # Get polling configuration (actual values being used)
    polling_config = {
        "poll_interval_fast": entry.options.get(
            CONF_POLL_INTERVAL_FAST, DEFAULT_POLL_INTERVAL_FAST
        ),
        "poll_interval_medium": entry.options.get(
            CONF_POLL_INTERVAL_MEDIUM, DEFAULT_POLL_INTERVAL_MEDIUM
        ),
        "poll_interval_slow": entry.options.get(
            CONF_POLL_INTERVAL_SLOW, DEFAULT_POLL_INTERVAL_SLOW
        ),
        "request_delay": entry.options.get(CONF_REQUEST_DELAY, DEFAULT_REQUEST_DELAY),
        "request_timeout": entry.options.get(
            CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT
        ),
    }

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "device_info": async_redact_data(device_info, TO_REDACT),
        "polling_config": polling_config,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_success_time": _format_datetime(last_success_time),
            "time_since_last_success": time_since_success,
            "diagnostics_generated_at": _format_datetime(now),
        },
        "coordinator_data": async_redact_data(
            coordinator.data if coordinator.data else {}, TO_REDACT
        ),
        "last_exception": _format_exception(coordinator.last_exception),
    }
