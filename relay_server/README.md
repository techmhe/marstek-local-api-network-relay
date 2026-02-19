# Marstek Relay Server

A lightweight HTTP proxy server that enables Home Assistant to control Marstek
energy storage devices that are on a **different network segment** (e.g., an
IoT VLAN or a separate LAN).

## Architecture

```
Home Assistant (any network)
      │
      │  HTTP POST (JSON)
      ▼
Marstek Relay Server  ← deploy this on the IoT network
      │
      │  UDP (Marstek Open API)
      ▼
Marstek Device (Venus A/D/E etc.)
```

## Requirements

- Python 3.11+
- A small Linux machine (Raspberry Pi, NAS, VM, etc.) on the **same network as
  the Marstek device**
- The Marstek device must have **Open API enabled** in the Marstek app

## Installation

```bash
# 1. Create a dedicated user (optional but recommended)
sudo useradd -r -s /sbin/nologin marstek

# 2. Create installation directory
sudo mkdir -p /opt/marstek-relay
sudo chown marstek:marstek /opt/marstek-relay

# 3. Copy files
sudo cp marstek_relay.py /opt/marstek-relay/
sudo cp marstek_relay.service /etc/systemd/system/

# 4. Create Python virtual environment and install dependencies
sudo -u marstek python3 -m venv /opt/marstek-relay/venv
sudo -u marstek /opt/marstek-relay/venv/bin/pip install aiohttp>=3.9.0

# 5. (Optional) Install psutil for multi-interface broadcast discovery
sudo -u marstek /opt/marstek-relay/venv/bin/pip install psutil

# 6. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable marstek-relay
sudo systemctl start marstek-relay

# 7. Check service status
sudo systemctl status marstek-relay
```

## Configuration

The server is configured via command-line arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| `--host` | `0.0.0.0` | HTTP bind address |
| `--port` | `8765` | HTTP port |
| `--udp-port` | `30000` | UDP port for Marstek discovery broadcasts |
| `--api-key` | *(none)* | Optional API key for security (`X-API-Key` header) |
| `--log-level` | `INFO` | Logging verbosity |

Edit `/etc/systemd/system/marstek-relay.service` to change arguments, then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart marstek-relay
```

### Security

It is **strongly recommended** to set an API key:

```ini
ExecStart=/opt/marstek-relay/venv/bin/python marstek_relay.py \
    --api-key "your-secret-key-here"
```

Set the same key in the Home Assistant integration options when configuring the
relay connection.

## API Endpoints

### `GET /health`

Health check.

```json
{"status": "ok", "version": "1.0.0", "udp_port": 30000}
```

### `POST /api/command`

Forward a single Marstek UDP command to a device.

**Request:**
```json
{
  "host": "192.168.10.50",
  "port": 30000,
  "message": "{\"id\":1,\"method\":\"ES.GetMode\",\"params\":{\"id\":0}}",
  "timeout": 10.0
}
```

**Response (success):**
```json
{"response": {"id": 1, "src": "...", "result": {"mode": "Auto", ...}}}
```

**Response (timeout):**
```json
{"error": "No response from 192.168.10.50:30000 within 10.0s"}
```

### `POST /api/status`

Get complete device status (relay server makes multiple UDP calls internally).

**Request:**
```json
{
  "host": "192.168.10.50",
  "port": 30000,
  "timeout": 2.5,
  "include_pv": false,
  "include_wifi": false,
  "include_em": true,
  "include_bat": false,
  "delay_between_requests": 2.0
}
```

**Response:**
```json
{"status": {"device_mode": "Auto", "battery_soc": 75, ...}}
```

### `POST /api/discover`

Broadcast UDP discovery for Marstek devices on the local network.

**Request:**
```json
{"timeout": 10.0}
```

**Response:**
```json
{
  "devices": [
    {
      "device_type": "VenusE 3.0",
      "version": 111,
      "ip": "192.168.10.50",
      "ble_mac": "aabbccddeeff",
      "wifi_mac": "112233445566"
    }
  ]
}
```

## Firewall

Allow inbound TCP traffic on port 8765 (or your configured port) from the
Home Assistant host:

```bash
# UFW example
sudo ufw allow from <HA_IP> to any port 8765

# iptables example
sudo iptables -A INPUT -s <HA_IP> -p tcp --dport 8765 -j ACCEPT
```

## Troubleshooting

- **No devices found during discovery**: Ensure the relay server and the
  Marstek device are on the **same network segment** (same broadcast domain).
- **Command timeouts**: Check that UDP port 30000 is not blocked between the
  relay server and the Marstek device.
- **Authentication errors**: Verify the API key matches what is configured in
  Home Assistant.
- **Logs**: `sudo journalctl -u marstek-relay -f`
