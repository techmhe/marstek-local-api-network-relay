"""The Marstek integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_RELAY_API_KEY,
    CONF_RELAY_URL,
    CONNECTION_TYPE_LOCAL,
    CONNECTION_TYPE_RELAY,
    DATA_SUPPRESS_RELOADS,
    DATA_UDP_CLIENT,
    DEFAULT_UDP_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MarstekDataUpdateCoordinator
from .pymarstek import MarstekClientProtocol, MarstekRelayClient, MarstekUDPClient, get_es_mode
from .scanner import MarstekScanner
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class MarstekRuntimeData:
    """Runtime data for Marstek integration."""

    coordinator: MarstekDataUpdateCoordinator
    device_info: dict[str, Any]


type MarstekConfigEntry = ConfigEntry[MarstekRuntimeData]


def _issue_id_for_entry(entry: ConfigEntry) -> str:
    """Build issue id for a config entry."""
    return f"cannot_connect_{entry.entry_id}"


def _create_connection_issue(
    hass: HomeAssistant, entry: ConfigEntry, host: str, error: str
) -> None:
    """Create a fixable connection issue for the entry."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id_for_entry(entry),
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="cannot_connect",
        translation_placeholders={"host": host, "error": error},
        data={"entry_id": entry.entry_id},
    )


def _clear_connection_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear a connection issue for the entry if present."""
    issue_registry = ir.async_get(hass)
    issue_id = _issue_id_for_entry(entry)
    if issue_registry.async_get_issue(DOMAIN, issue_id):
        issue_registry.async_delete(DOMAIN, issue_id)


def _get_shared_udp_client(hass: HomeAssistant) -> MarstekClientProtocol | None:
    """Get the shared UDP/relay client if it exists."""
    client = hass.data.get(DOMAIN, {}).get(DATA_UDP_CLIENT)
    if client is not None:
        return cast(MarstekClientProtocol, client)
    return None


async def _async_cleanup_last_entry(hass: HomeAssistant) -> None:
    """Clean up shared resources when the last entry unloads."""
    udp_client = _get_shared_udp_client(hass)
    if udp_client:
        await udp_client.async_cleanup()

    # Stop scanner before resetting singleton to ensure clean state on reload
    scanner = MarstekScanner.async_get(hass)
    await scanner.async_unload()
    MarstekScanner.async_reset()

    # Remove domain data entirely when last entry is unloaded
    hass.data.pop(DOMAIN, None)



async def _get_or_create_shared_udp_client(hass: HomeAssistant) -> MarstekUDPClient:
    """Get existing shared UDP client or create a new one.

    All Marstek config entries share a single UDP client to avoid port conflicts.
    Multiple sockets bound to the same port with SO_REUSEADDR causes response
    routing issues where responses go to the wrong socket.
    """
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if DATA_UDP_CLIENT not in hass.data[DOMAIN]:
        _LOGGER.debug("Creating shared UDP client for Marstek integration")
        udp_client = MarstekUDPClient()
        await udp_client.async_setup()
        hass.data[DOMAIN][DATA_UDP_CLIENT] = udp_client

    client: MarstekUDPClient = hass.data[DOMAIN][DATA_UDP_CLIENT]
    return client


async def _create_relay_client(
    hass: HomeAssistant, entry: ConfigEntry
) -> MarstekRelayClient:
    """Create a relay client for the given config entry."""
    relay_url: str = entry.data.get(CONF_RELAY_URL, "")
    api_key: str | None = entry.data.get(CONF_RELAY_API_KEY) or None
    session = async_get_clientsession(hass)
    client = MarstekRelayClient(relay_url, session, api_key=api_key)
    await client.async_setup()
    return client


async def _async_verify_device_connection(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: MarstekClientProtocol,
    host: str,
    port: int,
) -> None:
    """Verify device connectivity using a lightweight API request."""
    try:
        _LOGGER.info("Attempting connection to %s:%s", host, port)
        await client.send_request(
            get_es_mode(0),
            host,
            port,
            timeout=5.0,  # Increased timeout for initial connection
        )
        _LOGGER.info(
            "Connection successful to device at %s - using config_entry data",
            host,
        )
    except (TimeoutError, OSError, ValueError) as ex:
        error_type = type(ex).__name__
        _LOGGER.debug(
            "Unable to connect to device at %s (%s: %s). "
            "Scanner will detect IP changes automatically. "
            "Home Assistant will retry setup periodically.",
            host,
            error_type,
            str(ex),
        )
        _create_connection_issue(hass, entry, host, str(ex))
        raise ConfigEntryNotReady(
            f"Unable to connect to device at {host} ({error_type}: {ex}). "
            "Scanner will detect IP changes and update configuration automatically. "
            "Home Assistant will retry setup periodically."
        ) from ex


def _build_device_info_dict(
    entry: ConfigEntry,
    host: str,
    port: int,
) -> dict[str, Any]:
    """Build device info dictionary from config entry data."""
    return {
        "ip": host,
        "port": port,
        "mac": entry.data.get("mac", ""),
        "device_type": entry.data.get("device_type", "Unknown"),
        "version": entry.data.get("version", 0),
        "wifi_name": entry.data.get("wifi_name", ""),
        "wifi_mac": entry.data.get("wifi_mac", ""),
        "ble_mac": entry.data.get("ble_mac", ""),
    }


async def _async_setup_coordinator(
    hass: HomeAssistant,
    entry: MarstekConfigEntry,
    client: MarstekClientProtocol,
    device_info: dict[str, Any],
) -> MarstekDataUpdateCoordinator:
    """Create and refresh the coordinator, raising ConfigEntryNotReady on failure."""
    coordinator = MarstekDataUpdateCoordinator(
        hass,
        entry,
        client,
        device_info["ip"],
        device_info.get("port", DEFAULT_UDP_PORT),
        is_initial_setup=True,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        failures = getattr(coordinator, "consecutive_failures", 0)
        last_attempt = getattr(coordinator, "last_update_attempt_time", None)

        _LOGGER.debug(
            "Initial data fetch failed for %s after %d attempt(s) (last attempt: %s): %s",
            device_info["ip"],
            failures,
            last_attempt.isoformat() if last_attempt else "unknown",
            err,
        )
        _create_connection_issue(hass, entry, device_info["ip"], str(err))
        raise ConfigEntryNotReady(
            f"Initial data fetch failed for {device_info['ip']}: {err}. "
            "The device responded to connection check but failed to return status data. "
            "This may be temporary - Home Assistant will retry automatically."
        ) from err

    coordinator.finish_initial_setup()
    return coordinator


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Marstek component."""
    # Register services
    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: MarstekConfigEntry) -> bool:
    """Set up Marstek from a config entry."""
    _LOGGER.info("Setting up Marstek config entry: %s", entry.title)

    await async_setup_services(hass)

    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)
    is_relay = connection_type == CONNECTION_TYPE_RELAY

    if not is_relay:
        # Initialize scanner (only once, regardless of number of config entries)
        # Scanner will detect IP changes and update config entries via config flow
        scanner = MarstekScanner.async_get(hass)
        await scanner.async_setup()

    stored_ip = entry.data[CONF_HOST]
    stored_port = entry.data.get(CONF_PORT, DEFAULT_UDP_PORT)
    # Only use BLE-MAC for device identification (user feedback)
    stored_ble_mac = entry.data.get("ble_mac")

    _LOGGER.info(
        "Starting setup: attempting to connect to device at IP %s (BLE-MAC: %s, mode: %s)",
        stored_ip,
        stored_ble_mac or "unknown",
        connection_type,
    )

    # Create the appropriate client (relay or direct UDP)
    if is_relay:
        try:
            active_client: MarstekClientProtocol = await _create_relay_client(hass, entry)
        except (OSError, ValueError) as ex:
            error_type = type(ex).__name__
            relay_url = entry.data.get(CONF_RELAY_URL, "unknown")
            _create_connection_issue(hass, entry, relay_url, str(ex))
            raise ConfigEntryNotReady(
                f"Cannot reach relay server at {relay_url} ({error_type}: {ex}). "
                "Verify the relay server is running and reachable."
            ) from ex
        # Store relay client per-entry (not shared)
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}
        hass.data[DOMAIN][DATA_UDP_CLIENT] = active_client
        entry.async_on_unload(active_client.async_cleanup)
    else:
        # Use shared UDP client to avoid port conflicts between multiple devices
        udp_client = await _get_or_create_shared_udp_client(hass)
        active_client = udp_client

    # Try to connect with stored IP (mik-laj feedback)
    # If we have an IP address in the configuration, we should always connect to that IP
    # Discovery is handled by Scanner, not here
    await _async_verify_device_connection(
        hass,
        entry,
        active_client,
        stored_ip,
        stored_port,
    )

    # Use device info from config_entry (saved during config flow)
    device_info_dict = _build_device_info_dict(entry, stored_ip, stored_port)

    # Create coordinator in __init__.py (mik-laj feedback)
    # Use is_initial_setup=True for faster API request delays during first data fetch
    coordinator = await _async_setup_coordinator(
        hass,
        entry,
        active_client,
        device_info_dict,
    )

    # Clear any prior connection issue after successful setup
    _clear_connection_issue(hass, entry)

    # Store coordinator and device_info in runtime_data
    # Note: UDP client is shared via hass.data[DOMAIN][DATA_UDP_CLIENT]
    entry.runtime_data = MarstekRuntimeData(
        coordinator=coordinator,
        device_info=device_info_dict,
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MarstekConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Marstek config entry: %s", entry.title)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clear any repair issues tied to this entry
    _clear_connection_issue(hass, entry)

    # Check if this is the last LOADED config entry
    # (unloaded entries still exist in registry with NOT_LOADED state)
    remaining_entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state == ConfigEntryState.LOADED
    ]

    if not remaining_entries:
        await _async_cleanup_last_entry(hass)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: MarstekConfigEntry) -> None:
    """Remove a config entry and clean up stale devices."""
    from homeassistant.helpers.device_registry import format_mac

    # Clear any remaining repair issues
    _clear_connection_issue(hass, entry)

    device_identifier_raw = (
        entry.data.get("ble_mac")
        or entry.data.get("mac")
        or entry.data.get("wifi_mac")
    )
    if not device_identifier_raw:
        return

    # Use format_mac for consistency with build_device_info
    device_identifier = format_mac(device_identifier_raw)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, device_identifier)}
    )
    if not device:
        return

    remaining_entries = set(device.config_entries) - {entry.entry_id}
    if not remaining_entries:
        _LOGGER.info("Removing stale device registry entry: %s", device.name)
        device_registry.async_remove_device(device.id)


async def _async_update_listener(hass: HomeAssistant, entry: MarstekConfigEntry) -> None:
    """Handle options updates by reloading the entry."""
    suppress = hass.data.get(DOMAIN, {}).get(DATA_SUPPRESS_RELOADS)
    if suppress and entry.entry_id in suppress:
        suppress.discard(entry.entry_id)
        _LOGGER.debug(
            "Skipping reload for entry %s (metadata-only update)", entry.entry_id
        )
        return
    await hass.config_entries.async_reload(entry.entry_id)
