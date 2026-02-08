"""Select helper utilities for Marstek integration."""

from __future__ import annotations

import asyncio
import logging

from ..pymarstek import MarstekUDPClient

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_TIMEOUT = 5.0
RETRY_DELAY = 1.0


def _log_success(logger: logging.Logger, option: str, attempt: int) -> None:
    logger.info(
        "Successfully set operating mode to %s (attempt %d/%d)",
        option,
        attempt,
        MAX_RETRY_ATTEMPTS,
    )


def _log_failure(logger: logging.Logger, option: str, attempt: int, err: Exception) -> None:
    logger.warning(
        "Failed to set operating mode to %s (attempt %d/%d): %s",
        option,
        attempt,
        MAX_RETRY_ATTEMPTS,
        err,
    )


async def send_mode_command_with_retries(
    udp_client: MarstekUDPClient,
    command: str,
    host: str,
    port: int,
    option: str,
    *,
    logger: logging.Logger,
) -> str | None:
    """Send mode command with retries, returning last error on failure."""
    last_error: str | None = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            await udp_client.send_request(
                command,
                host,
                port,
                timeout=RETRY_TIMEOUT,
            )
            _log_success(logger, option, attempt)
            return None
        except (TimeoutError, OSError, ValueError) as err:
            _log_failure(logger, option, attempt, err)
            last_error = str(err)
            if attempt < MAX_RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY)
    return last_error
