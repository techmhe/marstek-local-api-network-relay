"""Network helpers for pymarstek."""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Mapping
from typing import Protocol

_LOGGER = logging.getLogger(__name__)


class PsutilAddress(Protocol):
    """Protocol for psutil address info objects."""

    family: int
    address: str
    broadcast: str | None
    netmask: str | None


class PsutilModule(Protocol):
    """Protocol for psutil module functions used here."""

    def net_if_addrs(self) -> Mapping[str, list[PsutilAddress]]: ...


def get_broadcast_addresses(
    *,
    psutil_module: PsutilModule | None = None,
    logger: logging.Logger | None = None,
    allow_import: bool = True,
) -> list[str]:
    """Get broadcast addresses for all network interfaces."""
    addresses: set[str] = {"255.255.255.255"}

    if logger is None:
        logger = _LOGGER

    if psutil_module is None:
        if not allow_import:
            logger.debug("psutil not available, using only global broadcast")
            return list(addresses)
        try:
            import importlib

            psutil_module = importlib.import_module("psutil")
        except Exception:
            logger.debug("psutil not available, using only global broadcast")
            return list(addresses)

    if psutil_module is None:
        logger.debug("psutil not available, using only global broadcast")
        return list(addresses)

    try:
        for addrs in psutil_module.net_if_addrs().values():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    broadcast = getattr(addr, "broadcast", None)
                    if isinstance(broadcast, str):
                        addresses.add(broadcast)
                        continue
                    netmask = getattr(addr, "netmask", None)
                    if isinstance(netmask, str):
                        try:
                            network = ipaddress.IPv4Network(
                                f"{addr.address}/{netmask}", strict=False
                            )
                            addresses.add(str(network.broadcast_address))
                        except (ValueError, OSError):
                            continue
    except OSError as err:
        logger.warning("Failed to get network interfaces: %s", err)

    try:
        local_ips = {
            addr.address
            for addrs in psutil_module.net_if_addrs().values()
            for addr in addrs
            if addr.family == socket.AF_INET
        }
        addresses -= local_ips
    except OSError:
        pass

    return list(addresses)
