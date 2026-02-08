"""Select entity descriptions for Marstek devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntityDescription

from ..const import OPERATING_MODES


@dataclass(kw_only=True)
class MarstekSelectEntityDescription(SelectEntityDescription):  # type: ignore[misc]
    """Marstek select entity description."""

    options_fn: Callable[[], list[str]]
    value_fn: Callable[[dict[str, Any]], str | None]


SELECT_ENTITIES: tuple[MarstekSelectEntityDescription, ...] = (
    MarstekSelectEntityDescription(
        key="operating_mode",
        translation_key="operating_mode",
        options_fn=lambda: OPERATING_MODES,
        value_fn=lambda data: data.get("device_mode"),
    ),
)
