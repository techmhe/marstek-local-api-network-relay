# Mock Marstek Device

A mock Marstek device for testing the Home Assistant integration without a real device. Includes realistic battery simulation with dynamic SOC changes, power fluctuations, and mode transitions.

## Features

- **Dynamic Battery Simulation**: SOC increases/decreases based on power flow
- **Power Fluctuations**: Realistic ±5% variations in power readings
- **Mode Support**: Auto, AI, Manual, and Passive modes with proper behavior
- **Passive Mode Timer**: Automatic expiration after configured duration
- **Manual Schedules**: Supports schedule slots with day/time configuration
- **Status Display**: Periodic console output showing current battery state

## Usage

### Standalone (for testing on your machine)

```bash
cd /Users/thomastheunen/Documents/Projects/ha_marstek
python3 tools/mock_device/mock_marstek.py
```

Options:
- `--port PORT` - UDP port (default: 30000)
- `--ip IP` - Override reported IP address
- `--device TYPE` - Device type (default: "VenusE 3.0")
- `--ble-mac MAC` - BLE MAC address
- `--wifi-mac MAC` - WiFi MAC address
- `--soc PERCENT` - Initial battery SOC percentage (default: 50)
- `--no-simulate` - Disable dynamic simulation (static values only)

### Examples

```bash
# Start with 30% battery (will start charging in Auto mode)
python3 tools/mock_device/mock_marstek.py --soc 30

# Start with 90% battery (will start discharging in Auto mode)
python3 tools/mock_device/mock_marstek.py --soc 90

# Static mode (no simulation, useful for predictable testing)
python3 tools/mock_device/mock_marstek.py --no-simulate
```

### With Docker Compose (devcontainer)

The devcontainer automatically starts a mock device at `172.28.0.20`.

When you open the devcontainer:
1. Home Assistant runs at `172.28.0.10` (accessible at http://localhost:8123)
2. Mock Marstek device runs at `172.28.0.20:30000`

To add the mock device in Home Assistant:
1. Go to Settings → Devices & Services
2. Add Integration → Marstek
3. If discovery doesn't find it, use manual entry with IP: `172.28.0.20`

## Simulation Behavior

### Auto Mode
- SOC < 30%: Charges at ~1500W
- SOC > 80%: Discharges at ~800W
- Otherwise: Idle

### AI Mode
- Similar to Auto with random variations
- SOC < 25%: Charges at 1000-2000W
- SOC > 85%: Discharges at 500-1000W

### Passive Mode
- Uses configured power and duration
- Automatically switches back to Auto when timer expires

### Manual Mode
- Follows configured schedule slots
- Checks current day/time against schedule settings

### SOC Limits
- Cannot discharge below 5% SOC
- Cannot charge above 100% SOC
- Power tapers as approaching limits

## Supported Methods

The mock device responds to:
- `Marstek.GetDevice` - Returns device info (used for discovery)
- `ES.GetStatus` - Returns battery status (SOC, power, mode, status)
- `ES.GetMode` - Returns current mode configuration with power readings
- `ES.SetMode` - Updates mode with passive_cfg or manual_cfg support
- `PV.GetStatus` - Returns PV panel status (always 0 in mock)

## Testing Discovery

From inside the devcontainer:
```bash
# Test broadcast discovery
python3 /workspaces/ha_marstek/tools/debug_udp_discovery.py --verbose

# Test direct query
python3 /workspaces/ha_marstek/tools/query_device.py 172.28.0.20
```

## Console Output

When running with simulation enabled, every 5 seconds you'll see:
```
[STATUS] SOC: 45% | Power: -1523W | Mode: Auto | ⚡ Charging
```

Whenever a request is received:
```
[14:32:05] Request from 172.28.0.10:54321
   Method: ES.GetMode
   ID: 1
   -> Sent response: ES.GetMode
```

Mode changes are logged:
```
[SIM] Mode set to: Passive
[SIM] Passive: power=-2000W, duration=3600s
```
