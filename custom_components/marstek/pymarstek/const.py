"""Constants for the pymarstek library."""

from __future__ import annotations

from typing import Final

DEFAULT_UDP_PORT: Final = 30000
DISCOVERY_TIMEOUT: Final = 10.0

CMD_DISCOVER: Final = "Marstek.GetDevice"
CMD_BATTERY_STATUS: Final = "Bat.GetStatus"
CMD_ES_STATUS: Final = "ES.GetStatus"
CMD_ES_MODE: Final = "ES.GetMode"
CMD_ES_SET_MODE: Final = "ES.SetMode"
CMD_PV_GET_STATUS: Final = "PV.GetStatus"
CMD_WIFI_STATUS: Final = "Wifi.GetStatus"
CMD_EM_STATUS: Final = "EM.GetStatus"
