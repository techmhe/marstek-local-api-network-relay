#!/usr/bin/env python3
"""Marstek Relay Server.

A lightweight HTTP proxy server that forwards commands from Home Assistant
to a Marstek energy storage device via UDP. Deploy this on a Linux machine
that is on the same network as the Marstek device.

Architecture:
    Home Assistant (any network)
        ↓ HTTP POST /api/command  (JSON)
    Marstek Relay Server  (IoT network)
        ↓ UDP JSON (Marstek Open API)
    Marstek Device

Usage:
    python marstek_relay.py [--host 0.0.0.0] [--port 8765]
                            [--api-key SECRET] [--udp-port 30000]

Requirements:
    pip install aiohttp>=3.9.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
import time
from typing import Any

from aiohttp import web

__version__ = "1.0.0"

_LOGGER = logging.getLogger(__name__)

# Default configuration
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8765
DEFAULT_UDP_PORT = 30000
DEFAULT_UDP_TIMEOUT = 10.0
DISCOVERY_TIMEOUT = 10.0
DISCOVERY_METHOD = "Marstek.GetDevice"

# Rate limiting
MIN_REQUEST_INTERVAL = 0.3  # seconds between requests to the same device


class RelayUDPClient:
    """Minimal async UDP client for forwarding commands to Marstek devices."""

    def __init__(self, udp_port: int = DEFAULT_UDP_PORT) -> None:
        self._udp_port = udp_port
        self._sock: socket.socket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_request_time: dict[str, float] = {}

    async def setup(self) -> None:
        """Set up the UDP socket."""
        self._loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        # No explicit bind - OS auto-assigns an ephemeral port on first sendto
        self._sock = sock
        _LOGGER.debug("UDP client socket created")

    async def close(self) -> None:
        """Close the UDP socket."""
        if self._sock:
            self._sock.close()
            self._sock = None

    async def _enforce_rate_limit(self, host: str) -> None:
        """Enforce minimum interval between requests to the same device."""
        now = time.monotonic()
        last = self._last_request_time.get(host, 0.0)
        elapsed = now - last
        if elapsed < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time[host] = time.monotonic()

    async def send_command(
        self,
        host: str,
        port: int,
        message: str,
        timeout: float = DEFAULT_UDP_TIMEOUT,
    ) -> dict[str, Any]:
        """Send a UDP command to a device and return the response.

        Args:
            host: Device IP address.
            port: Device UDP port.
            message: JSON string to send.
            timeout: Response wait timeout in seconds.

        Returns:
            Parsed JSON response from device.

        Raises:
            TimeoutError: If no response received within timeout.
            OSError: On socket errors.
            ValueError: If response is not valid JSON.
        """
        if self._sock is None or self._loop is None:
            await self.setup()
        assert self._sock is not None
        assert self._loop is not None

        await self._enforce_rate_limit(host)

        # Parse message to get request ID
        msg_obj: dict[str, Any] = json.loads(message)
        request_id: int | str = msg_obj["id"]

        data = message.encode("utf-8")
        self._sock.sendto(data, (host, port))
        _LOGGER.debug("UDP → %s:%d | %s", host, port, message)

        # Wait for response matching our request ID
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                recv_data, addr = await asyncio.wait_for(
                    self._loop.sock_recvfrom(self._sock, 4096),
                    timeout=min(remaining, 1.0),
                )
                response_text = recv_data.decode("utf-8")
                try:
                    response: dict[str, Any] = json.loads(response_text)
                except json.JSONDecodeError as exc:
                    _LOGGER.warning("Invalid JSON response: %s", exc)
                    continue
                _LOGGER.debug("UDP ← %s:%d | %s", addr[0], addr[1], response_text[:200])
                if isinstance(response, dict) and response.get("id") == request_id:
                    return response
            except TimeoutError:
                continue

        raise TimeoutError(f"No response from {host}:{port} within {timeout}s")

    async def discover_devices(
        self, timeout: float = DISCOVERY_TIMEOUT
    ) -> list[dict[str, Any]]:
        """Broadcast discovery and collect device responses.

        Args:
            timeout: Time to wait for responses in seconds.

        Returns:
            List of discovered device info dicts.
        """
        if self._sock is None or self._loop is None:
            await self.setup()
        assert self._sock is not None
        assert self._loop is not None

        request = {
            "id": 0,
            "method": DISCOVERY_METHOD,
            "params": {"ble_mac": "0"},
        }
        message = json.dumps(request)
        data = message.encode("utf-8")

        # Send to all broadcast addresses
        broadcast_addresses = _get_broadcast_addresses()
        for addr in broadcast_addresses:
            try:
                self._sock.sendto(data, (addr, self._udp_port))
                _LOGGER.debug("Broadcast → %s:%d", addr, self._udp_port)
            except OSError as err:
                _LOGGER.warning("Broadcast to %s failed: %s", addr, err)

        devices: list[dict[str, Any]] = []
        seen_macs: set[str] = set()
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                recv_data, src_addr = await asyncio.wait_for(
                    self._loop.sock_recvfrom(self._sock, 4096),
                    timeout=min(remaining, 0.5),
                )
                response_text = recv_data.decode("utf-8")
                try:
                    response = json.loads(response_text)
                except json.JSONDecodeError:
                    continue

                # Filter echoes (our own sent broadcast reflected back)
                if not isinstance(response, dict) or "result" not in response:
                    continue

                result = response.get("result", {})
                if not isinstance(result, dict):
                    continue

                ble_mac = result.get("ble_mac", "")
                if ble_mac in seen_macs:
                    continue
                seen_macs.add(ble_mac)

                device_ip = result.get("ip") or src_addr[0]
                device_info: dict[str, Any] = {
                    "device_type": result.get("device", "Unknown"),
                    "version": result.get("ver", 0),
                    "wifi_name": result.get("wifi_name", ""),
                    "ip": device_ip,
                    "wifi_mac": result.get("wifi_mac", ""),
                    "ble_mac": ble_mac,
                    "mac": result.get("wifi_mac") or ble_mac,
                    "model": result.get("device", "Unknown"),
                    "firmware": str(result.get("ver", 0)),
                }
                devices.append(device_info)
                _LOGGER.info(
                    "Discovered device: %s at %s",
                    device_info["device_type"],
                    device_ip,
                )
            except TimeoutError:
                continue

        _LOGGER.info("Discovery complete: found %d device(s)", len(devices))
        return devices


def _get_broadcast_addresses() -> list[str]:
    """Get broadcast addresses for all network interfaces."""
    addresses = ["255.255.255.255"]  # Global broadcast always included
    try:
        import psutil  # type: ignore[import-not-found]

        for _iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.broadcast:
                    bcast = str(addr.broadcast)
                    if bcast not in addresses:
                        addresses.append(bcast)
    except ImportError:
        _LOGGER.debug("psutil not available, using global broadcast only")
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not enumerate network interfaces: %s", err)
    return addresses


class MarstekRelayServer:
    """HTTP server that relays Home Assistant requests to Marstek devices via UDP."""

    def __init__(
        self,
        udp_client: RelayUDPClient,
        api_key: str | None = None,
    ) -> None:
        self._udp = udp_client
        self._api_key = api_key
        self._app = web.Application(middlewares=[self._auth_middleware])
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_post("/api/command", self._handle_command)
        self._app.router.add_post("/api/discover", self._handle_discover)
        self._app.router.add_post("/api/status", self._handle_status)

    @web.middleware
    async def _auth_middleware(
        self,
        request: web.Request,
        handler: Any,
    ) -> web.Response:
        """Optional API key authentication middleware."""
        if self._api_key:
            provided = request.headers.get("X-API-Key", "")
            if provided != self._api_key:
                _LOGGER.warning(
                    "Unauthorized request from %s: invalid API key",
                    request.remote,
                )
                return web.json_response(
                    {"error": "Unauthorized"}, status=401
                )
        return await handler(request)  # type: ignore[return-value]

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET /health - health check."""
        return web.json_response(
            {
                "status": "ok",
                "version": __version__,
                "udp_port": self._udp._udp_port,
            }
        )

    async def _handle_command(self, request: web.Request) -> web.Response:
        """POST /api/command - forward a single UDP command.

        Request body:
            host: Device IP address
            port: Device UDP port (default 30000)
            message: JSON string (Marstek API command)
            timeout: Response timeout in seconds (default 10.0)

        Response:
            {"response": {...}}  on success
            {"error": "..."}     on failure
        """
        try:
            body: dict[str, Any] = await request.json()
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": f"Invalid JSON body: {err}"}, status=400)

        host = body.get("host", "")
        port = int(body.get("port", DEFAULT_UDP_PORT))
        message = body.get("message", "")
        timeout = float(body.get("timeout", DEFAULT_UDP_TIMEOUT))

        if not host or not message:
            return web.json_response(
                {"error": "Missing required fields: host, message"}, status=400
            )

        _LOGGER.debug(
            "Command request from %s: %s:%d timeout=%.1fs",
            request.remote,
            host,
            port,
            timeout,
        )

        try:
            response = await self._udp.send_command(host, port, message, timeout)
            return web.json_response({"response": response})
        except TimeoutError as err:
            _LOGGER.warning("Command timeout for %s:%d: %s", host, port, err)
            return web.json_response({"error": str(err)}, status=504)
        except (OSError, ValueError) as err:
            _LOGGER.error("Command error for %s:%d: %s", host, port, err)
            return web.json_response({"error": str(err)}, status=502)

    async def _handle_discover(self, request: web.Request) -> web.Response:
        """POST /api/discover - broadcast discovery for Marstek devices.

        Request body (optional):
            timeout: Discovery timeout in seconds (default 10.0)

        Response:
            {"devices": [...]}
        """
        try:
            body: dict[str, Any] = await request.json() if request.can_read_body else {}
        except Exception:  # noqa: BLE001
            body = {}

        timeout = float(body.get("timeout", DISCOVERY_TIMEOUT))

        _LOGGER.info("Discovery request from %s (timeout=%.1fs)", request.remote, timeout)

        try:
            devices = await self._udp.discover_devices(timeout)
            return web.json_response({"devices": devices})
        except OSError as err:
            _LOGGER.error("Discovery failed: %s", err)
            return web.json_response({"error": str(err)}, status=502)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """POST /api/status - get full device status (multiple UDP calls).

        Request body:
            host: Device IP address
            port: Device UDP port (default 30000)
            timeout: Per-request timeout (default 2.5)
            include_pv: Fetch PV data (default false)
            include_wifi: Fetch WiFi data (default false)
            include_em: Fetch energy meter data (default true)
            include_bat: Fetch battery details (default false)
            delay_between_requests: Delay between UDP calls (default 2.0)

        Response:
            {"status": {...}}  on success
            {"error": "..."}   on failure
        """
        try:
            body: dict[str, Any] = await request.json()
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": f"Invalid JSON body: {err}"}, status=400)

        host = body.get("host", "")
        port = int(body.get("port", DEFAULT_UDP_PORT))
        timeout = float(body.get("timeout", 2.5))
        include_pv = bool(body.get("include_pv", False))
        include_wifi = bool(body.get("include_wifi", False))
        include_em = bool(body.get("include_em", True))
        include_bat = bool(body.get("include_bat", False))
        delay_between = float(body.get("delay_between_requests", 2.0))

        if not host:
            return web.json_response({"error": "Missing required field: host"}, status=400)

        _LOGGER.debug(
            "Status request from %s for %s:%d (pv=%s wifi=%s em=%s bat=%s)",
            request.remote,
            host,
            port,
            include_pv,
            include_wifi,
            include_em,
            include_bat,
        )

        try:
            status = await _get_device_status(
                self._udp,
                host,
                port,
                timeout=timeout,
                include_pv=include_pv,
                include_wifi=include_wifi,
                include_em=include_em,
                include_bat=include_bat,
                delay_between=delay_between,
            )
            return web.json_response({"status": status})
        except TimeoutError as err:
            _LOGGER.warning("Status timeout for %s:%d: %s", host, port, err)
            return web.json_response({"error": str(err)}, status=504)
        except (OSError, ValueError) as err:
            _LOGGER.error("Status error for %s:%d: %s", host, port, err)
            return web.json_response({"error": str(err)}, status=502)


async def _get_device_status(
    udp: RelayUDPClient,
    host: str,
    port: int,
    *,
    timeout: float = 2.5,
    include_pv: bool = False,
    include_wifi: bool = False,
    include_em: bool = True,
    include_bat: bool = False,
    delay_between: float = 2.0,
) -> dict[str, Any]:
    """Fetch and merge device status from multiple UDP calls.

    This mirrors the logic in MarstekUDPClient.get_device_status() so the
    relay server can be used with a single HTTP call per poll cycle instead
    of multiple individual /api/command calls.
    """
    made_request = False
    collected: dict[str, Any] = {}

    async def _fetch(method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal made_request
        if made_request:
            await asyncio.sleep(delay_between)
        msg = json.dumps({"id": 1, "method": method, "params": params})
        try:
            response = await udp.send_command(host, port, msg, timeout)
            made_request = True
            result = response.get("result")
            if isinstance(result, dict):
                return result
            return None
        except (TimeoutError, OSError, ValueError) as err:
            _LOGGER.debug("%s failed for %s: %s", method, host, err)
            return None

    # Fast tier – always fetch
    es_mode = await _fetch("ES.GetMode", {"id": 0})
    if es_mode:
        collected["device_mode"] = es_mode.get("mode")
        collected["ongrid_power"] = es_mode.get("ongrid_power")
        collected["offgrid_power"] = es_mode.get("offgrid_power")
        collected["battery_soc"] = es_mode.get("bat_soc")

    es_status = await _fetch("ES.GetStatus", {"id": 0})
    if es_status:
        if es_status.get("bat_soc") is not None:
            collected["battery_soc"] = es_status["bat_soc"]
        collected["battery_power"] = es_status.get("bat_power")
        collected["pv_power"] = es_status.get("pv_power")
        collected["battery_cap"] = es_status.get("bat_cap")

    if include_em:
        em_status = await _fetch("EM.GetStatus", {"id": 0})
        if em_status:
            collected["ct_state"] = em_status.get("ct_state")
            collected["ct_connected"] = bool(em_status.get("ct_state"))
            collected["em_a_power"] = em_status.get("a_power")
            collected["em_b_power"] = em_status.get("b_power")
            collected["em_c_power"] = em_status.get("c_power")
            collected["em_total_power"] = em_status.get("total_power")

    if include_pv:
        pv_status = await _fetch("PV.GetStatus", {"id": 0})
        if pv_status:
            collected["pv1_power"] = pv_status.get("pv_power")
            collected["pv1_voltage"] = pv_status.get("pv_voltage")
            collected["pv1_current"] = pv_status.get("pv_current")

    if include_wifi:
        wifi_status = await _fetch("Wifi.GetStatus", {"id": 0})
        if wifi_status:
            collected["wifi_rssi"] = wifi_status.get("rssi")
            collected["wifi_ssid"] = wifi_status.get("ssid")
            collected["wifi_sta_ip"] = wifi_status.get("sta_ip")
            collected["wifi_sta_gate"] = wifi_status.get("sta_gate")
            collected["wifi_sta_mask"] = wifi_status.get("sta_mask")
            collected["wifi_sta_dns"] = wifi_status.get("sta_dns")

    if include_bat:
        bat_status = await _fetch("Bat.GetStatus", {"id": 0})
        if bat_status:
            collected["bat_temp"] = bat_status.get("bat_temp")
            collected["bat_charg_flag"] = bat_status.get("charg_flag")
            collected["bat_dischrg_flag"] = bat_status.get("dischrg_flag")
            collected["bat_remaining_capacity"] = bat_status.get("bat_capacity")
            collected["bat_rated_capacity"] = bat_status.get("rated_capacity")
            if bat_status.get("soc") is not None:
                collected.setdefault("battery_soc", bat_status["soc"])

    return collected


async def run_server(
    http_host: str = DEFAULT_HTTP_HOST,
    http_port: int = DEFAULT_HTTP_PORT,
    udp_port: int = DEFAULT_UDP_PORT,
    api_key: str | None = None,
) -> None:
    """Run the relay server."""
    udp_client = RelayUDPClient(udp_port=udp_port)
    await udp_client.setup()

    server = MarstekRelayServer(udp_client, api_key=api_key)

    runner = web.AppRunner(server._app)
    await runner.setup()

    site = web.TCPSite(runner, http_host, http_port)
    await site.start()

    _LOGGER.info(
        "Marstek Relay Server v%s started on http://%s:%d (UDP port %d)%s",
        __version__,
        http_host,
        http_port,
        udp_port,
        " [API key required]" if api_key else "",
    )

    try:
        # Run forever
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
        await udp_client.close()
        _LOGGER.info("Marstek Relay Server stopped")


def main() -> None:
    """Entry point for the relay server."""
    parser = argparse.ArgumentParser(
        description="Marstek Relay Server - forwards HA commands to Marstek devices via UDP",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HTTP_HOST,
        help="HTTP server bind address",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="HTTP server port",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=DEFAULT_UDP_PORT,
        help="UDP port for Marstek device discovery broadcasts",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional API key for request authentication (X-API-Key header)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        asyncio.run(
            run_server(
                http_host=args.host,
                http_port=args.port,
                udp_port=args.udp_port,
                api_key=args.api_key,
            )
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
