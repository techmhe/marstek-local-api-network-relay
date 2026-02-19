# Installation

## HACS (recommended)

1. Open **HACS** in Home Assistant.
2. **Custom repositories** → add this repository as **Integration**.
3. Search for **Marstek** and install.
4. Restart Home Assistant.

## Manual

1. Copy `custom_components/marstek` into your HA config folder as `config/custom_components/marstek`.
2. Restart Home Assistant.

## Requirements checklist

- Home Assistant Core **2025.10+**
- **Open API enabled** in the Marstek app
- UDP **port 30000** reachable between HA (or the relay host) and the device

## Cross-network / VLAN setup

If Home Assistant is on a **different network segment** than the Marstek device
(e.g., management VLAN vs. IoT VLAN), you need to deploy the **relay server**
on a machine that *can* reach the device, and then configure the integration to
use it.

See the full guide: [Relay server setup](relay.md)
