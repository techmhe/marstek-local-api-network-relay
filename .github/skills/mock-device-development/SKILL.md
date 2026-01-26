---
name: mock-device-development
description: Guide for developing and maintaining mock Marstek battery devices for local testing and devcontainer environments
---

# Mock Marstek Device Development

This skill covers creating, configuring, and maintaining mock Marstek devices for testing the Home Assistant integration without physical hardware.

## Overview

Mock devices simulate real Marstek batteries (Venus A/D/E 3.0) using UDP on port 30000. They implement the same Open API protocol as real devices, enabling full integration testing.

## Key Files

| File | Purpose |
|------|---------|
| `tools/mock_device/mock_marstek.py` | Main mock device implementation |
| `tools/mock_device/Dockerfile` | Container image for devcontainer |
| `.devcontainer/docker-compose.yml` | Multi-device orchestration |

## Multi-Battery Setup

The devcontainer supports multiple mock devices for testing multi-battery scenarios:

```yaml
# .devcontainer/docker-compose.yml
mock-marstek:
  command: ["python", "mock_marstek.py", "--ip", "172.28.0.20"]

mock-marstek-2:
  command: ["python", "mock_marstek.py", "--ip", "172.28.0.21", "--ble-mac", "009b08a5bb40", "--soc", "75"]

mock-marstek-3:
  command: ["python", "mock_marstek.py", "--ip", "172.28.0.22", "--ble-mac", "009b08a5cc41", "--soc", "30"]
```

### Adding a New Mock Device

1. Add service to `docker-compose.yml`:
   - Unique container name
   - Unique IP in `172.28.0.0/16` subnet
   - Unique BLE MAC (used as device unique_id)
   - Optional: different initial SOC

2. Required CLI flags:
   - `--ip` - Must match the container's `ipv4_address`
   - `--ble-mac` - Must be unique per device (12 hex chars, no colons)
   - `--wifi-mac` - Optional, but should be unique

## Simulation Architecture

### BatterySimulator Class

Manages realistic battery behavior:

```
┌─────────────────────────────────────────────────────────┐
│                   BatterySimulator                      │
├─────────────────────────────────────────────────────────┤
│ SOC: 0-100%          │ Updates every 1 second          │
│ Capacity: 5120Wh     │ Power fluctuation: ±5%          │
│ Max charge: 3000W    │ Reserve threshold: 5%           │
│ Max discharge: 3000W │ Charge taper: >90% SOC          │
└─────────────────────────────────────────────────────────┘
```

### HouseholdSimulator Class

Generates realistic power consumption patterns:

| Time of Day | Base Load | Events |
|-------------|-----------|--------|
| 6-9 (morning) | 200-500W | Breakfast appliances |
| 9-17 (day) | 50-150W | Occasional appliances |
| 17-22 (evening) | 300-800W | Cooking, TV, lights |
| 22-6 (night) | 0-50W | Standby loads |

Random events: cooking (1500-3000W), washing machine, dryer, microwave, etc.

### Mode Behaviors

| Mode | Behavior |
|------|----------|
| **Auto** | Discharges to offset household consumption (grid_power → 0) |
| **AI** | Like Auto but saves energy for evening peaks |
| **Passive** | Fixed power for set duration, then reverts to Auto |
| **Manual** | Follows schedule slots (day/time/power) |

## CLI Reference

```bash
python mock_marstek.py [OPTIONS]

--port PORT        UDP port (default: 30000)
--ip IP            Reported IP address (must match container IP)
--device TYPE      Device type string (default: "VenusE 3.0")
--ble-mac MAC      BLE MAC address, 12 hex chars (default: 009b08a5aa39)
--wifi-mac MAC     WiFi MAC address, 12 hex chars
--soc PERCENT      Initial SOC 0-100 (default: 50)
--no-simulate      Disable dynamic simulation (static values)
```

## Supported API Methods

| Method | Response |
|--------|----------|
| `Marstek.GetDevice` | Device info (discovery) |
| `ES.GetStatus` | SOC, power, grid_power, energies |
| `ES.GetMode` | Current mode, power readings |
| `ES.SetMode` | Mode change with passive_cfg/manual_cfg |
| `PV.GetStatus` | PV panel readings (always 0) |
| `Wifi.GetStatus` | WiFi RSSI, SSID, IP config |
| `EM.GetStatus` | CT clamp / energy meter readings |
| `Bat.GetStatus` | Battery temp, charge/discharge flags |

## Testing in Devcontainer

```bash
# Test discovery broadcast
python3 /workspaces/ha_marstek/tools/debug_udp_discovery.py --verbose

# Query specific device
python3 /workspaces/ha_marstek/tools/query_device.py 172.28.0.20

# View mock device logs
docker logs marstek-mock-device -f
docker logs marstek-mock-device-2 -f
```

## Adding New API Methods

1. Add handler in `_build_response()` method
2. Match response structure from `docs/marstek_device_openapi.MD`
3. Use `self._get_state()` for current battery state
4. Test with `tools/query_device.py`

Example:
```python
elif method == "NewMethod.GetData":
    state = self._get_state()
    return {
        "id": request_id,
        "src": src,
        "result": {
            "some_field": state["soc"],
        },
    }
```

## Debugging Tips

- Console shows status every 5 seconds when simulation enabled
- All requests/responses are logged with timestamps
- Mode changes logged with `[SIM]` prefix
- Household events logged with `[HOUSE]` prefix

## When to Modify

- Adding new sensor entities that need mock data
- Testing multi-battery aggregation
- Validating mode control commands
- Reproducing specific battery states
