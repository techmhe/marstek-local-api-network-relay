"""Command builder utilities for pymarstek."""

from __future__ import annotations

import json
from typing import Any

from .const import (
    CMD_BATTERY_STATUS,
    CMD_DISCOVER,
    CMD_EM_STATUS,
    CMD_ES_MODE,
    CMD_ES_SET_MODE,
    CMD_ES_STATUS,
    CMD_PV_GET_STATUS,
    CMD_WIFI_STATUS,
)

_request_id = 0


def get_next_request_id() -> int:
    """Get the next request identifier."""
    global _request_id  # noqa: PLW0603 - internal counter
    _request_id += 1
    return _request_id


def reset_request_id() -> None:
    """Reset the request identifier counter."""
    global _request_id  # noqa: PLW0603 - internal counter
    _request_id = 0


def build_command(method: str, params: dict[str, Any] | None = None) -> str:
    """Construct a JSON command payload."""
    command = {
        "id": get_next_request_id(),
        "method": method,
        "params": params or {},
    }
    return json.dumps(command)


def discover() -> str:
    """Create a discovery command."""
    return build_command(CMD_DISCOVER, {"ble_mac": "0"})


def get_battery_status(device_id: int = 0) -> str:
    """Create a battery status command."""
    return build_command(CMD_BATTERY_STATUS, {"id": device_id})


def get_es_status(device_id: int = 0) -> str:
    """Create an ES status command."""
    return build_command(CMD_ES_STATUS, {"id": device_id})


def get_es_mode(device_id: int = 0) -> str:
    """Create an ES mode command."""
    return build_command(CMD_ES_MODE, {"id": device_id})


def get_pv_status(device_id: int = 0) -> str:
    """Create a PV status command."""
    return build_command(CMD_PV_GET_STATUS, {"id": device_id})


def set_es_mode_manual_charge(device_id: int = 0, power: int = -1300) -> str:
    """Create a manual charge command."""
    config = {
        "mode": "Manual",
        "manual_cfg": {
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,
            "power": power,
            "enable": 1,
        },
    }
    return build_command(CMD_ES_SET_MODE, {"id": device_id, "config": config})


def set_es_mode_manual_discharge(device_id: int = 0, power: int = 1300) -> str:
    """Create a manual discharge command."""
    config = {
        "mode": "Manual",
        "manual_cfg": {
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,
            "power": power,
            "enable": 1,
        },
    }
    return build_command(CMD_ES_SET_MODE, {"id": device_id, "config": config})


def get_wifi_status(device_id: int = 0) -> str:
    """Create a WiFi status command."""
    return build_command(CMD_WIFI_STATUS, {"id": device_id})


def get_em_status(device_id: int = 0) -> str:
    """Create an Energy Meter (CT) status command."""
    return build_command(CMD_EM_STATUS, {"id": device_id})
