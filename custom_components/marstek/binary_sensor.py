"""Binary sensor platform for Marstek devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
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
from .const import DOMAIN
from .coordinator import MarstekDataUpdateCoordinator


class MarstekCTConnectionBinarySensor(
    CoordinatorEntity[MarstekDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a Marstek CT connection binary sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "ct_connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        device_info: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the CT connection binary sensor."""
        super().__init__(coordinator)
        self._device_info = device_info
        self._config_entry = config_entry

        device_identifier_raw = (
            device_info.get("ble_mac")
            or device_info.get("mac")
            or device_info.get("wifi_mac")
        )
        if not device_identifier_raw:
            raise ValueError("Marstek device identifier (MAC) is required")
        device_identifier = format_mac(device_identifier_raw)

        device_ip = (
            config_entry.data.get(CONF_HOST)
            if config_entry
            else device_info.get("ip", "Unknown")
        )

        self._attr_unique_id = f"{device_identifier}_ct_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_identifier)},
            name=f"Marstek {device_info['device_type']} v{device_info['version']} ({device_ip})",
            manufacturer="Marstek",
            model=device_info["device_type"],
            sw_version=str(device_info["version"]),
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if CT is connected."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("ct_connected")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MarstekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Marstek binary sensors based on a config entry."""
    coordinator = config_entry.runtime_data.coordinator
    device_info = config_entry.runtime_data.device_info

    entities: list[BinarySensorEntity] = [
        MarstekCTConnectionBinarySensor(coordinator, device_info, config_entry),
    ]

    async_add_entities(entities)
