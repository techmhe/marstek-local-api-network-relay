"""Shared client protocol for Marstek device clients.

Both MarstekUDPClient (direct UDP) and MarstekRelayClient (HTTP relay)
implement this protocol, allowing the coordinator and other modules to
work with either transport without changes.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MarstekClientProtocol(Protocol):
    """Protocol for Marstek device communication clients."""

    async def async_setup(self) -> None:  # pragma: no cover
        """Initialize the client (open socket / verify connectivity)."""
        ...

    async def async_cleanup(self) -> None:  # pragma: no cover
        """Release resources held by this client."""
        ...

    def is_polling_paused(self, device_ip: str) -> bool:  # pragma: no cover
        """Return True if polling is currently paused for device_ip."""
        ...

    async def pause_polling(self, device_ip: str) -> None:  # pragma: no cover
        """Pause coordinator polling for device_ip."""
        ...

    async def resume_polling(self, device_ip: str) -> None:  # pragma: no cover
        """Resume coordinator polling for device_ip."""
        ...

    async def get_device_status(
        self,
        device_ip: str,
        port: int = 30000,
        timeout: float = 2.5,
        *,
        include_pv: bool = True,
        include_wifi: bool = True,
        include_em: bool = True,
        include_bat: bool = True,
        delay_between_requests: float = 2.0,
        previous_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:  # pragma: no cover
        """Fetch and return merged device status."""
        ...

    async def send_request(
        self,
        message: str,
        target_ip: str,
        target_port: int,
        timeout: float = 5.0,
        *,
        quiet_on_timeout: bool = False,
        validate: bool = True,
    ) -> dict[str, Any]:  # pragma: no cover
        """Send a raw command and return the response."""
        ...

    def get_command_stats_for_ip(
        self, device_ip: str
    ) -> dict[str, dict[str, Any]]:  # pragma: no cover
        """Return per-command diagnostics stats for device_ip."""
        ...
