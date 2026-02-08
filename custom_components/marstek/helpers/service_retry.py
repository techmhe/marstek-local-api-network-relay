"""Service retry helpers for Marstek integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from ..const import CMD_ES_SET_MODE, DOMAIN
from ..pymarstek import MarstekUDPClient, build_command

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_TIMEOUT = 5.0
RETRY_DELAY = 1.0


def _log_success(logger: logging.Logger, attempt: int) -> None:
    logger.info(
        "Successfully sent mode command (attempt %d/%d)",
        attempt,
        MAX_RETRY_ATTEMPTS,
    )


def _log_failure(logger: logging.Logger, attempt: int, err: Exception) -> None:
    logger.warning(
        "Failed to send mode command (attempt %d/%d): %s",
        attempt,
        MAX_RETRY_ATTEMPTS,
        err,
    )


async def send_mode_command_with_retries(
    udp_client: MarstekUDPClient,
    host: str,
    port: int,
    config: dict[str, Any],
    *,
    pause_polling: bool = True,
    logger: logging.Logger,
) -> None:
    """Send a mode command with retries, raising on failure."""
    command = build_command(CMD_ES_SET_MODE, {"id": 0, "config": config})

    if pause_polling:
        await udp_client.pause_polling(host)

    try:
        last_error: str | None = None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                await udp_client.send_request(
                    command,
                    host,
                    port,
                    timeout=RETRY_TIMEOUT,
                )
                _log_success(logger, attempt)
                return
            except (TimeoutError, OSError, ValueError) as err:
                last_error = str(err)
                _log_failure(logger, attempt, err)
                if attempt < MAX_RETRY_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY)

        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": last_error or "Unknown error"},
        )
    finally:
        if pause_polling:
            await udp_client.resume_polling(host)
