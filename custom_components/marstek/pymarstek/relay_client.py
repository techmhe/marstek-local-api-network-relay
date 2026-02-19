"""HTTP relay client for the Marstek integration.

This client communicates with a Marstek Relay Server instead of sending
UDP packets directly. It allows Home Assistant to control Marstek devices
that are on a different network segment (e.g. an IoT VLAN).

Architecture:
    Home Assistant (any network)
          ↓  HTTP POST /api/command  (JSON)
    MarstekRelayClient
          ↓  HTTP POST /api/status
    Marstek Relay Server  (same network as device)
          ↓  UDP (Marstek Open API)
    Marstek Device
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

import aiohttp

from .const import DEFAULT_UDP_PORT
from .data_parser import merge_device_status
from .validators import ValidationError, validate_json_message

_LOGGER = logging.getLogger(__name__)

_RELAY_CONNECT_TIMEOUT = 5.0   # seconds - initial reachability check
_RELAY_COMMAND_OVERHEAD = 5.0  # extra seconds on top of UDP timeout for HTTP round-trip


class MarstekRelayClient:
    """Client that forwards Marstek commands to a relay server via HTTP.

    Args:
        relay_url: Base URL of the relay server, e.g. ``http://192.168.1.100:8765``.
        session: Shared :class:`aiohttp.ClientSession` (obtained from HA helper).
        api_key: Optional API key sent as ``X-API-Key`` header.
    """

    def __init__(
        self,
        relay_url: str,
        session: aiohttp.ClientSession,
        api_key: str | None = None,
    ) -> None:
        self._relay_url = relay_url.rstrip("/")
        self._session = session
        self._api_key = api_key

        self._polling_paused: dict[str, bool] = {}
        self._polling_lock: asyncio.Lock = asyncio.Lock()

        # Minimal diagnostics (method → stats)
        self._command_stats: dict[str, dict[str, Any]] = {}

    def _headers(self) -> dict[str, str]:
        """Build request headers, including optional API key."""
        if self._api_key:
            return {"X-API-Key": self._api_key}
        return {}

    async def async_setup(self) -> None:
        """Verify connectivity to the relay server."""
        url = f"{self._relay_url}/health"
        try:
            async with self._session.get(
                url,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=_RELAY_CONNECT_TIMEOUT),
            ) as resp:
                if resp.status == 401:
                    raise ValueError(
                        f"Relay server at {self._relay_url} rejected the API key (401)."
                    )
                resp.raise_for_status()
                _LOGGER.info(
                    "Connected to Marstek relay server at %s", self._relay_url
                )
        except aiohttp.ClientError as err:
            raise OSError(
                f"Cannot reach relay server at {url}: {err}"
            ) from err

    async def async_cleanup(self) -> None:
        """No-op: the aiohttp session is managed by Home Assistant."""

    # ------------------------------------------------------------------
    # Polling pause/resume (local state, identical to MarstekUDPClient)
    # ------------------------------------------------------------------

    def is_polling_paused(self, device_ip: str) -> bool:
        """Return True if polling is currently paused for device_ip."""
        return self._polling_paused.get(device_ip, False)

    async def pause_polling(self, device_ip: str) -> None:
        """Pause coordinator polling for device_ip."""
        async with self._polling_lock:
            self._polling_paused[device_ip] = True

    async def resume_polling(self, device_ip: str) -> None:
        """Resume coordinator polling for device_ip."""
        async with self._polling_lock:
            self._polling_paused[device_ip] = False

    # ------------------------------------------------------------------
    # Device communication
    # ------------------------------------------------------------------

    async def send_request(
        self,
        message: str,
        target_ip: str,
        target_port: int,
        timeout: float = 5.0,
        *,
        quiet_on_timeout: bool = False,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Forward a raw command to the device via the relay server.

        Args:
            message: JSON command string (Marstek API format).
            target_ip: Device IP address.
            target_port: Device UDP port.
            timeout: Per-request timeout in seconds.
            quiet_on_timeout: If True, do not log warnings on timeout.
            validate: If True, validate the message before sending.

        Returns:
            Response dict from the device.

        Raises:
            ValidationError: If validation is enabled and the message is invalid.
            TimeoutError: If the relay server reports a device timeout.
            OSError: On HTTP connectivity errors.
        """
        if validate:
            try:
                validate_json_message(message)
            except ValidationError:
                _LOGGER.error(
                    "Relay: request validation failed for %s:%d",
                    target_ip,
                    target_port,
                )
                raise

        method_name = "unknown"
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            method_name = str(json.loads(message).get("method", "unknown"))

        payload: dict[str, Any] = {
            "host": target_ip,
            "port": target_port,
            "message": message,
            "timeout": timeout,
        }
        http_timeout = aiohttp.ClientTimeout(total=timeout + _RELAY_COMMAND_OVERHEAD)

        try:
            async with self._session.post(
                f"{self._relay_url}/api/command",
                json=payload,
                headers=self._headers(),
                timeout=http_timeout,
            ) as resp:
                data: dict[str, Any] = await resp.json(content_type=None)

                if resp.status == 504 or "error" in data:
                    error_msg = str(data.get("error", "unknown relay error"))
                    if not quiet_on_timeout:
                        _LOGGER.warning(
                            "Relay command timeout for %s:%d [%s]: %s",
                            target_ip,
                            target_port,
                            method_name,
                            error_msg,
                        )
                    self._record_stat(method_name, success=False, timeout=True)
                    raise TimeoutError(error_msg)

                resp.raise_for_status()
                response: dict[str, Any] = data.get("response", {})
                self._record_stat(method_name, success=True, timeout=False)
                return response

        except aiohttp.ClientError as err:
            self._record_stat(method_name, success=False, timeout=False)
            raise OSError(f"Relay HTTP error for {target_ip}: {err}") from err

    async def get_device_status(
        self,
        device_ip: str,
        port: int = DEFAULT_UDP_PORT,
        timeout: float = 2.5,
        *,
        include_pv: bool = True,
        include_wifi: bool = True,
        include_em: bool = True,
        include_bat: bool = True,
        delay_between_requests: float = 2.0,
        previous_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fetch complete device status via relay server's /api/status endpoint.

        The relay server performs all internal UDP calls and returns the merged
        status, allowing the round-trip to be completed in a single HTTP call.

        Args:
            device_ip: Device IP address (as seen from the relay server).
            port: Device UDP port.
            timeout: Per-UDP-request timeout (relay handles individual calls).
            include_pv: Whether to fetch PV/solar data.
            include_wifi: Whether to fetch WiFi diagnostics.
            include_em: Whether to fetch energy meter / CT data.
            include_bat: Whether to fetch detailed battery data.
            delay_between_requests: Delay the relay inserts between UDP calls.
            previous_status: Previous status dict; returned values are merged
                so transient partial failures don't clear cached values.

        Returns:
            Merged device status dictionary compatible with the coordinator.
        """
        payload: dict[str, Any] = {
            "host": device_ip,
            "port": port,
            "timeout": timeout,
            "include_pv": include_pv,
            "include_wifi": include_wifi,
            "include_em": include_em,
            "include_bat": include_bat,
            "delay_between_requests": delay_between_requests,
        }

        # Allow generous HTTP timeout: relay needs to complete all UDP calls first
        calls = 2  # ES.GetMode + ES.GetStatus always
        if include_em:
            calls += 1
        if include_pv:
            calls += 1
        if include_wifi:
            calls += 1
        if include_bat:
            calls += 1
        estimated = calls * (timeout + delay_between_requests) + _RELAY_COMMAND_OVERHEAD
        http_timeout = aiohttp.ClientTimeout(total=estimated)

        try:
            async with self._session.post(
                f"{self._relay_url}/api/status",
                json=payload,
                headers=self._headers(),
                timeout=http_timeout,
            ) as resp:
                data: dict[str, Any] = await resp.json(content_type=None)

                if resp.status in (502, 504) or "error" in data:
                    error_msg = str(data.get("error", "relay status error"))
                    raise TimeoutError(error_msg)

                resp.raise_for_status()
                relay_status: dict[str, Any] = data.get("status", {})

        except aiohttp.ClientError as err:
            raise OSError(f"Relay HTTP error for {device_ip}: {err}") from err

        # Map relay server response fields to coordinator-expected keys, then
        # merge with previous_status to preserve values on partial failures.
        es_mode_data: dict[str, Any] | None = None
        es_status_data: dict[str, Any] | None = None

        if "device_mode" in relay_status:
            es_mode_data = {
                "device_mode": relay_status.get("device_mode"),
                "ongrid_power": relay_status.get("ongrid_power"),
                "offgrid_power": relay_status.get("offgrid_power"),
                "battery_soc": relay_status.get("battery_soc"),
            }

        if "battery_power" in relay_status:
            es_status_data = {
                "battery_soc": relay_status.get("battery_soc"),
                "battery_power": relay_status.get("battery_power"),
                "pv_power": relay_status.get("pv_power"),
                "battery_cap": relay_status.get("battery_cap"),
            }

        pv_status_data: dict[str, Any] | None = None
        if include_pv and "pv1_power" in relay_status:
            pv_status_data = {
                "pv1_power": relay_status.get("pv1_power"),
                "pv1_voltage": relay_status.get("pv1_voltage"),
                "pv1_current": relay_status.get("pv1_current"),
            }

        wifi_status_data: dict[str, Any] | None = None
        if include_wifi and "wifi_rssi" in relay_status:
            wifi_status_data = {
                "wifi_rssi": relay_status.get("wifi_rssi"),
                "wifi_ssid": relay_status.get("wifi_ssid"),
                "wifi_sta_ip": relay_status.get("wifi_sta_ip"),
                "wifi_sta_gate": relay_status.get("wifi_sta_gate"),
                "wifi_sta_mask": relay_status.get("wifi_sta_mask"),
                "wifi_sta_dns": relay_status.get("wifi_sta_dns"),
            }

        em_status_data: dict[str, Any] | None = None
        if include_em and "ct_state" in relay_status:
            em_status_data = {
                "ct_state": relay_status.get("ct_state"),
                "ct_connected": relay_status.get("ct_connected"),
                "em_a_power": relay_status.get("em_a_power"),
                "em_b_power": relay_status.get("em_b_power"),
                "em_c_power": relay_status.get("em_c_power"),
                "em_total_power": relay_status.get("em_total_power"),
            }

        bat_status_data: dict[str, Any] | None = None
        if include_bat and "bat_temp" in relay_status:
            bat_status_data = {
                "bat_temp": relay_status.get("bat_temp"),
                "bat_charg_flag": relay_status.get("bat_charg_flag"),
                "bat_dischrg_flag": relay_status.get("bat_dischrg_flag"),
                "bat_remaining_capacity": relay_status.get("bat_remaining_capacity"),
                "bat_rated_capacity": relay_status.get("bat_rated_capacity"),
            }

        status = merge_device_status(
            es_mode_data=es_mode_data,
            es_status_data=es_status_data,
            pv_status_data=pv_status_data,
            wifi_status_data=wifi_status_data,
            em_status_data=em_status_data,
            bat_status_data=bat_status_data,
            device_ip=device_ip,
            last_update=time.monotonic(),
            previous_status=previous_status,
        )
        status["has_fresh_data"] = bool(relay_status)
        return status

    async def discover_devices(self) -> list[dict[str, Any]]:
        """Discover Marstek devices via the relay server's broadcast.

        Returns:
            List of device info dicts as returned by the relay server.
        """
        try:
            async with self._session.post(
                f"{self._relay_url}/api/discover",
                json={"timeout": 10.0},
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=15.0),
            ) as resp:
                data: dict[str, Any] = await resp.json(content_type=None)
                resp.raise_for_status()
                devices: list[dict[str, Any]] = data.get("devices", [])
                return devices
        except aiohttp.ClientError as err:
            raise OSError(f"Relay discovery failed: {err}") from err

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_command_stats_for_ip(
        self, device_ip: str
    ) -> dict[str, dict[str, Any]]:
        """Return per-command diagnostics (limited in relay mode)."""
        return {}

    def _record_stat(
        self, method: str, *, success: bool, timeout: bool
    ) -> None:
        """Track basic success/failure counts per method."""
        bucket = self._command_stats.setdefault(
            method,
            {
                "total_attempts": 0,
                "total_success": 0,
                "total_timeouts": 0,
                "total_failures": 0,
            },
        )
        bucket["total_attempts"] += 1
        if success:
            bucket["total_success"] += 1
        elif timeout:
            bucket["total_timeouts"] += 1
        else:
            bucket["total_failures"] += 1
