"""Select platform for Marstek devices."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .pymarstek import MarstekUDPClient, build_command

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:
    from collections.abc import Iterable
    from typing import Protocol

    class AddConfigEntryEntitiesCallback(Protocol):
        def __call__(
            self,
            new_entities: Iterable,
            update_before_add: bool = False,
        ) -> None:
            """Define add_entities type."""

from . import MarstekConfigEntry
from .const import (
    CMD_ES_SET_MODE,
    DEFAULT_UDP_PORT,
    DOMAIN,
    MODE_AI,
    MODE_AUTO,
    MODE_MANUAL,
    MODE_PASSIVE,
    MODE_TO_API,
    OPERATING_MODES,
)
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_TIMEOUT = 5.0
RETRY_DELAY = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MarstekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Marstek select entities based on a config entry."""
    coordinator = config_entry.runtime_data.coordinator
    device_info = config_entry.runtime_data.device_info
    udp_client = config_entry.runtime_data.udp_client

    entities: list[SelectEntity] = [
        MarstekOperatingModeSelect(
            coordinator=coordinator,
            device_info=device_info,
            udp_client=udp_client,
            config_entry=config_entry,
        ),
    ]

    async_add_entities(entities)


class MarstekOperatingModeSelect(
    CoordinatorEntity[MarstekDataUpdateCoordinator], SelectEntity
):
    """Select entity for Marstek operating mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "operating_mode"

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        device_info: dict[str, Any],
        udp_client: MarstekUDPClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._device_info_dict = device_info
        self._udp_client = udp_client
        self._config_entry = config_entry

        # Use BLE-MAC as device identifier for stability
        device_identifier = (
            device_info.get("ble_mac")
            or device_info.get("mac")
            or device_info.get("wifi_mac")
        )
        if not device_identifier:
            raise ValueError("Marstek device identifier (MAC) is required")

        self._device_identifier = device_identifier
        self._attr_unique_id = f"{device_identifier}_operating_mode"

        # Get current IP for device name
        device_ip = config_entry.data.get(CONF_HOST, device_info.get("ip", "Unknown"))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_identifier)},
            name=f"Marstek {device_info['device_type']} v{device_info['version']} ({device_ip})",
            manufacturer="Marstek",
            model=device_info["device_type"],
            sw_version=str(device_info["version"]),
        )

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        return OPERATING_MODES

    @property
    def current_option(self) -> str | None:
        """Return the current operating mode."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("device_mode")

    async def async_select_option(self, option: str) -> None:
        """Change the operating mode."""
        if option not in OPERATING_MODES:
            raise HomeAssistantError(f"Invalid operating mode: {option}")

        host = self._config_entry.data.get(CONF_HOST)
        if not host:
            raise HomeAssistantError("Device IP address not configured")

        # Build mode configuration
        config = self._build_mode_config(option)

        # Build command
        command = build_command(CMD_ES_SET_MODE, {"id": 0, "config": config})

        # Pause polling while sending command
        await self._udp_client.pause_polling(host)

        try:
            success = False
            last_error: str | None = None

            for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
                try:
                    await self._udp_client.send_request(
                        command,
                        host,
                        DEFAULT_UDP_PORT,
                        timeout=RETRY_TIMEOUT,
                    )
                    _LOGGER.info(
                        "Successfully set operating mode to %s (attempt %d/%d)",
                        option,
                        attempt,
                        MAX_RETRY_ATTEMPTS,
                    )
                    success = True
                    break
                except (TimeoutError, OSError, ValueError) as err:
                    last_error = str(err)
                    _LOGGER.warning(
                        "Failed to set operating mode to %s (attempt %d/%d): %s",
                        option,
                        attempt,
                        MAX_RETRY_ATTEMPTS,
                        err,
                    )
                    if attempt < MAX_RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY)

            if not success:
                raise HomeAssistantError(
                    f"Failed to set operating mode to {option}: {last_error}"
                )

            # Request coordinator refresh to update state
            await self.coordinator.async_request_refresh()

        finally:
            await self._udp_client.resume_polling(host)

    def _build_mode_config(self, mode: str) -> dict[str, Any]:
        """Build the configuration payload for a mode."""
        # Convert HA mode to API mode value
        api_mode = MODE_TO_API.get(mode, mode)
        
        if mode == MODE_AUTO:
            return {
                "mode": api_mode,
                "auto_cfg": {"enable": 1},
            }
        elif mode == MODE_AI:
            return {
                "mode": api_mode,
                "ai_cfg": {"enable": 1},
            }
        elif mode == MODE_MANUAL:
            # Default manual config - user can customize via services
            return {
                "mode": api_mode,
                "manual_cfg": {
                    "time_num": 0,
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "week_set": 127,  # All days
                    "power": 0,
                    "enable": 0,  # Disabled by default - user sets via service
                },
            }
        elif mode == MODE_PASSIVE:
            # Default passive config - use services to set power/duration
            return {
                "mode": api_mode,
                "passive_cfg": {
                    "power": 0,  # No power by default
                    "cd_time": 3600,  # 1 hour default duration
                },
            }
        else:
            raise ValueError(f"Unknown mode: {mode}")
