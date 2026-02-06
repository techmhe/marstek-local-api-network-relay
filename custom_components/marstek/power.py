"""Power limit helpers for Marstek integration."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry

from .const import CONF_SOCKET_LIMIT, device_default_socket_limit, get_device_power_limits


def get_power_limits_for_entry(entry: ConfigEntry) -> tuple[int, int]:
    """Return min/max power limits for a config entry."""
    device_type = entry.data.get("device_type")
    socket_limit = entry.options.get(
        CONF_SOCKET_LIMIT,
        device_default_socket_limit(device_type),
    )
    return get_device_power_limits(device_type, socket_limit=socket_limit)


def validate_power_for_entry(
    entry: ConfigEntry,
    power: int,
    error_factory: Callable[[int, int, int], Exception],
) -> None:
    """Validate power against entry limits and raise provided error type."""
    min_power, max_power = get_power_limits_for_entry(entry)
    if power < min_power or power > max_power:
        raise error_factory(power, min_power, max_power)
