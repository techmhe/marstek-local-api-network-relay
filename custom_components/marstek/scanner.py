"""Scanner for Marstek devices - detects IP changes."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any, ClassVar, Self

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .discovery import discover_devices

_LOGGER = logging.getLogger(__name__)

# Scanner runs discovery every 10 minutes as a backup
# Primary detection is event-driven: triggered when coordinator hits failure threshold
SCAN_INTERVAL = timedelta(minutes=10)

# Minimum time between event-triggered scans (debounce)
MIN_SCAN_INTERVAL = timedelta(seconds=30)

# Minimum time between discovery flows for unconfigured devices
UNCONFIGURED_DISCOVERY_DEBOUNCE = timedelta(hours=1)


class MarstekScanner:
    """Scanner for Marstek devices that detects IP address changes."""

    _scanner: ClassVar[Self | None] = None

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the scanner."""
        self._hass = hass
        self._track_interval: CALLBACK_TYPE | None = None
        self._scan_task: asyncio.Task[None] | None = None
        self._last_scan_time: datetime | None = None
        self._unconfigured_seen: dict[str, datetime] = {}

    @classmethod
    @callback
    def async_get(cls, hass: HomeAssistant) -> Self:
        """Get singleton scanner instance."""
        if cls._scanner is None:
            cls._scanner = cls(hass)
        return cls._scanner

    @classmethod
    @callback
    def async_reset(cls) -> None:
        """Reset the singleton scanner instance.

        Should be called when the last config entry is unloaded to ensure
        clean state on reload and avoid stale references during testing.
        """
        cls._scanner = None

    async def async_setup(self) -> None:
        """Initialize scanner and start periodic scanning."""
        if self._track_interval is not None:
            _LOGGER.debug("Marstek scanner already initialized")
            return
        _LOGGER.info("Initializing Marstek scanner")
        # No need to create persistent UDP client - create new instance for each scan
        # This avoids state issues and conflicts with concurrent requests

        # Start periodic scanning
        self._track_interval = async_track_time_interval(
            self._hass,
            self.async_scan,
            SCAN_INTERVAL,
            cancel_on_shutdown=True,
        )

        # Execute initial scan immediately
        self.async_scan()

    async def async_unload(self) -> None:
        """Stop periodic scanning and cleanup resources."""
        if self._track_interval is not None:
            self._track_interval()
            self._track_interval = None
            _LOGGER.debug("Marstek scanner stopped")

        # Cancel any running scan task
        if self._scan_task is not None and not self._scan_task.done():
            self._scan_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._scan_task
            self._scan_task = None

    @callback
    def async_scan(self, now: datetime | None = None) -> None:
        """Periodically scan for devices and check IP changes."""
        # Cancel previous scan if still running (shouldn't happen normally)
        if self._scan_task is not None and not self._scan_task.done():
            _LOGGER.debug("Previous scan still running, skipping")
            return

        # Execute scan in background task (non-blocking)
        self._scan_task = self._hass.async_create_task(self._async_scan_impl())
        self._last_scan_time = datetime.now()

    @callback
    def async_request_scan(self) -> bool:
        """Request an immediate scan (event-driven, e.g., on connection failure).

        This allows the coordinator to trigger a scan when it detects connection
        failures, enabling faster IP change detection without aggressive polling.

        Returns:
            True if scan was triggered, False if debounced (too soon after last scan)
        """
        # Debounce: don't scan if we recently scanned
        if self._last_scan_time is not None:
            elapsed = datetime.now() - self._last_scan_time
            if elapsed < MIN_SCAN_INTERVAL:
                _LOGGER.debug(
                    "Scan request debounced (last scan %s ago, min interval %s)",
                    elapsed,
                    MIN_SCAN_INTERVAL,
                )
                return False

        _LOGGER.info("Immediate scan requested (connection failure detected)")
        self.async_scan()
        return True

    async def _async_scan_impl(self) -> None:
        """Execute device discovery and check for IP changes."""
        try:
            # Use local discovery module (workaround for pymarstek echo issues)
            _LOGGER.debug("Scanner: Starting device discovery (broadcast)")
            devices = await discover_devices()

            _LOGGER.debug(
                "Scanner: Discovered %d device(s)", len(devices) if devices else 0
            )

            if not devices:
                return

            # Log discovered devices for debugging
            _LOGGER.debug("Scanner: Discovered devices:")
            for device in devices:
                _LOGGER.debug(
                    "  Device: %s at IP %s (BLE-MAC: %s)",
                    device.get("device_type", "Unknown"),
                    device.get("ip", "Unknown"),
                    device.get("ble_mac", "N/A"),
                )

            # Check all configured entries for IP changes
            # Check both LOADED and SETUP_RETRY states (SETUP_RETRY means connection failed)
            for entry in self._hass.config_entries.async_entries(DOMAIN):
                _LOGGER.debug(
                    "Scanner: Checking entry %s (state: %s)",
                    entry.title,
                    entry.state,
                )
                if entry.state not in (
                    ConfigEntryState.LOADED,
                    ConfigEntryState.SETUP_RETRY,
                ):
                    _LOGGER.debug(
                        "Scanner: Skipping entry %s - state is %s (not LOADED)",
                        entry.title,
                        entry.state,
                    )
                    continue

                stored_ble_mac = entry.data.get("ble_mac")
                stored_ip = entry.data.get(CONF_HOST)

                _LOGGER.debug(
                    "Scanner: Entry %s - stored BLE-MAC: %s, stored IP: %s",
                    entry.title,
                    stored_ble_mac or "N/A",
                    stored_ip or "N/A",
                )

                if not stored_ble_mac or not stored_ip:
                    _LOGGER.debug(
                        "Scanner: Skipping entry %s - missing BLE-MAC or IP",
                        entry.title,
                    )
                    continue

                # Find matching device by BLE-MAC
                matched_device = self._find_device_by_ble_mac(
                    devices, stored_ble_mac, entry.title
                )

                if not matched_device:
                    _LOGGER.debug(
                        "Scanner: No matching device found for entry %s (BLE-MAC: %s)",
                        entry.title,
                        stored_ble_mac,
                    )
                    continue

                new_ip = matched_device.get("ip")
                _LOGGER.debug(
                    "Scanner: Entry %s - current IP: %s, discovered IP: %s",
                    entry.title,
                    stored_ip,
                    new_ip,
                )
                if new_ip and new_ip != stored_ip:
                    _LOGGER.info(
                        "Scanner detected IP change for device %s: %s -> %s",
                        stored_ble_mac,
                        stored_ip,
                        new_ip,
                    )
                    # Trigger discovery flow to update config entry (mik-laj feedback)
                    # This follows the pattern used in Yeelight integration
                    discovery_flow.async_create_flow(
                        self._hass,
                        DOMAIN,
                        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
                        data={
                            "ip": new_ip,
                            "ble_mac": stored_ble_mac,
                            "device_type": matched_device.get("device_type"),
                            "version": matched_device.get("version"),
                            "wifi_name": matched_device.get("wifi_name"),
                            "wifi_mac": matched_device.get("wifi_mac"),
                            "mac": matched_device.get("mac"),
                        },
                    )
                else:
                    _LOGGER.debug(
                        "Scanner: Entry %s IP unchanged (%s)",
                        entry.title,
                        stored_ip,
                    )

            # Trigger discovery flows for unconfigured devices
            configured_macs = self._get_configured_macs()
            self._prune_unconfigured_cache(configured_macs)
            self._trigger_unconfigured_discovery(devices, configured_macs)
        except Exception as err:
            _LOGGER.debug("Scanner discovery failed: %s", err)

    def _find_device_by_ble_mac(
        self, devices: list[dict[str, Any]], stored_ble_mac: str, entry_title: str
    ) -> dict[str, Any] | None:
        """Find device by BLE-MAC address."""
        for device in devices:
            device_ble_mac = device.get("ble_mac")
            if device_ble_mac:
                _LOGGER.debug(
                    "Scanner: Comparing stored BLE-MAC %s with device BLE-MAC %s",
                    format_mac(stored_ble_mac),
                    format_mac(device_ble_mac),
                )
                if format_mac(device_ble_mac) == format_mac(stored_ble_mac):
                    _LOGGER.debug(
                        "Scanner: BLE-MAC match found for entry %s",
                        entry_title,
                    )
                    return device
        return None

    def _get_configured_macs(self) -> set[str]:
        """Collect all configured MACs for this integration."""
        configured: set[str] = set()
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            for key in ("ble_mac", "mac", "wifi_mac"):
                value = entry.data.get(key)
                if not value:
                    continue
                try:
                    configured.add(format_mac(value))
                except (TypeError, ValueError):
                    continue
        return configured

    def _prune_unconfigured_cache(self, configured_macs: set[str]) -> None:
        """Drop cached unconfigured devices that are now configured."""
        for mac in list(self._unconfigured_seen):
            if mac in configured_macs:
                self._unconfigured_seen.pop(mac, None)

    def _has_pending_discovery(self, ble_mac: str) -> bool:
        """Return True if a discovery flow is already in progress for this device."""
        try:
            formatted = format_mac(ble_mac)
        except (TypeError, ValueError):
            return False

        flows = self._hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        for flow in flows:
            context = flow.get("context", {})
            if context.get("source") != config_entries.SOURCE_INTEGRATION_DISCOVERY:
                continue
            if context.get("unique_id") == formatted:
                return True
            data = flow.get("data", {})
            flow_ble_mac = data.get("ble_mac")
            if flow_ble_mac:
                try:
                    if format_mac(flow_ble_mac) == formatted:
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    def _should_trigger_unconfigured(self, ble_mac: str) -> bool:
        """Return True if we should trigger a discovery flow for this device."""
        if not ble_mac:
            return False
        try:
            formatted = format_mac(ble_mac)
        except (TypeError, ValueError):
            return False

        if self._has_pending_discovery(formatted):
            return False

        now = datetime.now()
        last_seen = self._unconfigured_seen.get(formatted)
        if last_seen and (now - last_seen) < UNCONFIGURED_DISCOVERY_DEBOUNCE:
            return False

        self._unconfigured_seen[formatted] = now
        return True

    def _trigger_unconfigured_discovery(
        self, devices: list[dict[str, Any]], configured_macs: set[str]
    ) -> None:
        """Create discovery flows for devices not yet configured."""
        for device in devices:
            device_ip = device.get("ip")
            device_ble_mac = device.get("ble_mac")
            if not device_ip or not device_ble_mac:
                continue

            try:
                formatted_mac = format_mac(device_ble_mac)
            except (TypeError, ValueError):
                continue

            if formatted_mac in configured_macs:
                continue

            if not self._should_trigger_unconfigured(formatted_mac):
                continue

            _LOGGER.info(
                "Scanner discovered unconfigured device %s at %s",
                formatted_mac,
                device_ip,
            )
            discovery_flow.async_create_flow(
                self._hass,
                DOMAIN,
                context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
                data={
                    "ip": device_ip,
                    "ble_mac": device_ble_mac,
                    "device_type": device.get("device_type"),
                    "version": device.get("version"),
                    "wifi_name": device.get("wifi_name"),
                    "wifi_mac": device.get("wifi_mac"),
                    "mac": device.get("mac"),
                },
            )
