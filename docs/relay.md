# Relay Server

The relay server lets Home Assistant communicate with Marstek devices that are
on a **different network segment** (e.g., an IoT VLAN) — a scenario where a
direct UDP broadcast from Home Assistant cannot reach the device.

## When do you need the relay?

| Scenario | Use relay? |
|---|---|
| HA and Marstek device on the same LAN / VLAN | **No** — use the default local connection |
| HA on a management network, device on an IoT VLAN | **Yes** |
| HA in a cloud/remote environment | **Yes** |

## Architecture

```
Home Assistant (any network)
      │
      │  HTTP POST (JSON)
      ▼
Marstek Relay Server  ← deploy on the IoT/device network
      │
      │  UDP (Marstek Open API, port 30000)
      ▼
Marstek Device (Venus A / D / E 3.0 etc.)
```

The relay server is a lightweight Python process (`relay_server/marstek_relay.py`)
that exposes an HTTP API and forwards commands to the device via UDP on your behalf.

---

## Step 1 — Install the relay server

Deploy the relay server on any small Linux machine (Raspberry Pi, NAS, VM, …)
that is on the **same network as your Marstek device**.

### Requirements

- Python 3.11+
- `aiohttp` ≥ 3.9.0 (installed in the steps below)
- `psutil` (optional — enables multi-interface broadcast discovery)

### Install steps

```bash
# 1. Create a dedicated user (optional but recommended)
sudo useradd -r -s /sbin/nologin marstek

# 2. Create the installation directory
sudo mkdir -p /opt/marstek-relay
sudo chown marstek:marstek /opt/marstek-relay

# 3. Copy the relay script
#    (from the relay_server/ folder of this repository)
sudo cp relay_server/marstek_relay.py /opt/marstek-relay/
sudo cp relay_server/marstek_relay.service /etc/systemd/system/

# 4. Create a Python virtual environment and install dependencies
sudo -u marstek python3 -m venv /opt/marstek-relay/venv
sudo -u marstek /opt/marstek-relay/venv/bin/pip install aiohttp>=3.9.0

# 5. (Optional) Install psutil for multi-interface broadcast discovery
sudo -u marstek /opt/marstek-relay/venv/bin/pip install psutil

# 6. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable marstek-relay
sudo systemctl start marstek-relay

# 7. Verify it is running
sudo systemctl status marstek-relay
```

Expected output in the service log:

```
Marstek Relay Server v1.0.0 started on http://0.0.0.0:8765 (UDP port 30000)
```

### Test the relay server

From any machine that can reach the relay host, check the health endpoint:

```bash
curl http://<RELAY_HOST_IP>:8765/health
# Expected: {"status": "ok", "version": "1.0.0", "udp_port": 30000}
```

### Configuration options

| Argument | Default | Description |
|---|---|---|
| `--host` | `0.0.0.0` | HTTP bind address |
| `--port` | `8765` | HTTP port |
| `--udp-port` | `30000` | UDP port used to reach Marstek devices |
| `--api-key` | *(none)* | Optional API key (`X-API-Key` header) |
| `--log-level` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

To change arguments, edit the `ExecStart` line in the service file and reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart marstek-relay
```

### Security — set an API key (recommended)

Edit `/etc/systemd/system/marstek-relay.service`:

```ini
ExecStart=/opt/marstek-relay/venv/bin/python marstek_relay.py \
    --host 0.0.0.0 \
    --port 8765 \
    --api-key "your-secret-key-here"
```

You will enter the **same key** when configuring the integration in Home Assistant
(see Step 2).

### Firewall

Allow inbound TCP on the relay port from the Home Assistant host:

```bash
# UFW
sudo ufw allow from <HA_IP> to any port 8765

# iptables
sudo iptables -A INPUT -s <HA_IP> -p tcp --dport 8765 -j ACCEPT
```

---

## Step 2 — Install the Home Assistant integration

Follow the standard [Installation](installation.md) steps (HACS or manual).
No extra steps are required for relay mode beyond installing the integration.

---

## Step 3 — Configure the integration with relay mode

1. Go to **Settings → Devices & Services**.
2. Click **Add Integration** and search for **Marstek**.
3. On the first screen, select **Via relay server (different network)** and click **Submit**.

   > If you do not see this option, make sure you are running a version of the
   > integration that includes relay support.

4. Enter the relay server URL and (optionally) the API key:

   | Field | Example | Notes |
   |---|---|---|
   | Relay server URL | `http://192.168.10.5:8765` | IP/hostname of the relay host, HTTP port |
   | API key | `your-secret-key-here` | Leave blank if you did not set `--api-key` |

5. Click **Submit**. The integration will contact the relay's `/health` endpoint
   to verify connectivity. If this fails, double-check the URL and that the
   service is running (`sudo systemctl status marstek-relay`).

6. The relay will run UDP broadcast discovery on its local network and present a
   list of found devices. Select your device and click **Submit**.

   If no devices are found, click **Enter IP manually** and provide the device's
   IP address directly.

7. The config entry is created. Entities will appear after the first polling
   cycle (up to 30 seconds with default settings).

---

## Troubleshooting

### Relay not reachable from Home Assistant

- Confirm the relay service is running: `sudo systemctl status marstek-relay`
- Test with `curl http://<RELAY_HOST_IP>:8765/health` from the HA host
- Check firewall rules allow TCP on port 8765

### No devices found during relay discovery

- Confirm the relay host and Marstek device are on the **same network segment**
  (same broadcast domain / VLAN)
- Confirm **Open API is enabled** in the Marstek app
- Check UDP port 30000 is not blocked between the relay host and the device
- Try the manual IP entry option

### Authentication errors (401)

- Verify the API key in the integration options matches `--api-key` on the relay

### Relay logs

```bash
sudo journalctl -u marstek-relay -f
```

Add `--log-level DEBUG` to the `ExecStart` line for verbose UDP logging.

---

## Advanced: running the relay without systemd

For testing or containers you can run the relay directly:

```bash
cd relay_server
pip install aiohttp>=3.9.0
python marstek_relay.py --log-level DEBUG
```

Or with Docker:

```bash
docker run --rm -p 8765:8765 --network host \
  -v "$(pwd)/relay_server:/app" \
  python:3.11-slim \
  python /app/marstek_relay.py --log-level DEBUG
```

> `--network host` is required so the relay can send UDP broadcasts on the
> host's network interfaces.
