"""Utilities for building mode configuration payloads."""

from __future__ import annotations

from typing import Any

from .const import (
    MODE_AI,
    MODE_AUTO,
    MODE_MANUAL,
    MODE_PASSIVE,
    MODE_TO_API,
    WEEKDAYS_ALL,
)


def build_mode_config(mode: str) -> dict[str, Any]:
    """Build the configuration payload for a mode.

    This is used for default select-based mode changes. Service calls can
    override these defaults with explicit parameters.
    """
    api_mode = MODE_TO_API.get(mode, mode)

    if mode == MODE_AUTO:
        return {
            "mode": api_mode,
            "auto_cfg": {"enable": 1},
        }

    if mode == MODE_AI:
        return {
            "mode": api_mode,
            "ai_cfg": {"enable": 1},
        }

    if mode == MODE_MANUAL:
        return {
            "mode": api_mode,
            "manual_cfg": {
                "time_num": 0,
                "start_time": "00:00",
                "end_time": "23:59",
                "week_set": WEEKDAYS_ALL,
                "power": 0,
                "enable": 0,
            },
        }

    if mode == MODE_PASSIVE:
        return {
            "mode": api_mode,
            "passive_cfg": {
                "power": 0,
                "cd_time": 3600,
            },
        }

    raise ValueError(f"Unknown mode: {mode}")
