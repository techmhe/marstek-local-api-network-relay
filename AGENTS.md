# Agent Protocol: Marstek (Home Assistant Custom Integration)

This repository contains a Home Assistant custom integration for **Marstek energy storage devices** (Venus A/D/E 3.0, etc.) using the **local “Open API” over UDP**.

## What this integration is (and is not)

- **Domain**: `marstek`
- **Scope**: Marstek devices that support **OPEN API** on the local network.
- **Transport**: UDP JSON-RPC-like messages (default port **30000**) as described in `docs/MarstekDeviceOpenApi.pdf`.
- **Pattern**: `local_polling` using a single `DataUpdateCoordinator` per device + a background `Scanner` to detect IP changes.

Important compatibility notes:
- The integration is currently **not compatible with Venus E2.0** devices (see `README.md`).

## Architectural constraints you must respect

### 1) Keep polling centralized
- Do **not** add per-entity polling or extra network calls from entities.
- All entities must read from `MarstekDataUpdateCoordinator.data`.
- Avoid concurrent requests; Marstek devices can be sensitive to request bursts.

If you add/modify device control:
- Pause coordinator polling while sending control commands (see `custom_components/marstek/device_action.py`) to avoid concurrent UDP traffic.

### 2) Async-only I/O
- Never use blocking I/O.
- All network operations must be awaited and run in the event loop.

### 3) Home Assistant integration contract
- Config/UI-first: no new YAML setup; keep config/reauth/options in `config_flow.py` with selectors where it improves UX.
- Unique IDs must stay stable (BLE-MAC-based) to prevent duplicate entities on IP changes.
- Add user-facing text via `strings.json` → mirrored to `translations/en.json`; prefer descriptive error keys (e.g., `cannot_connect`).
- Entity classes should set `_attr_has_entity_name = True` and expose `device_info` for proper device grouping.
- Loading must be async and non-blocking; any sync library work belongs in executor jobs.

### 4) Discovery and IP changes are handled by the scanner
- Setup/connection uses the configured IP; it does **not** perform discovery during setup.
- `MarstekScanner` runs periodic broadcast discovery and triggers an integration discovery flow to update the config entry when IP changes.
- Don’t add “fallback discovery” inside coordinator updates; it creates race conditions and extra traffic.

### 5) OPEN API semantics (UDP)
- Devices must have OPEN API enabled in the Marstek app.
- Default UDP port is 30000; the Open API spec recommends using a high port range.
- LAN discovery uses UDP broadcast + `Marstek.GetDevice` (see `docs/MarstekDeviceOpenApi.pdf`).

## Code map (where to implement changes)

| Concern | File | Notes |
|---|---|---|
| Setup / teardown | `custom_components/marstek/__init__.py` | Creates UDP client + coordinator; starts `MarstekScanner`; forwards platforms |
| Config flow | `custom_components/marstek/config_flow.py` | Broadcast discovery UI, DHCP updates, and integration-discovery handling |
| Polling + error handling | `custom_components/marstek/coordinator.py` | Single source of truth for status polling; returns previous data on connectivity issues |
| IP change detection | `custom_components/marstek/scanner.py` | Periodic broadcast discovery; triggers discovery flow to update config entries |
| Entities | `custom_components/marstek/sensor.py` | Coordinator-backed sensors; stable unique IDs based on BLE-MAC |
| Device actions | `custom_components/marstek/device_action.py` | Implements device automation actions using `ES.SetMode` with retries + verification; pauses polling during control |
| Text/translations | `custom_components/marstek/strings.json`, `custom_components/marstek/translations/en.json` | Keep translation keys stable |
| Local API reference | `docs/MarstekDeviceOpenApi.pdf` | UDP protocol + method list (Marstek.GetDevice, ES.GetStatus, ES.GetMode, etc.) |

## Adding or changing sensors

Preferred pattern:
1. Ensure the value is present on `MarstekDataUpdateCoordinator.data`.
2. Add a coordinator-backed `SensorEntity` in `sensor.py`.
3. Keep unique IDs stable (BLE-MAC based) so upgrades don’t duplicate entities.
4. Add/adjust translation keys in `translations/en.json` and keep `strings.json` in sync.

## Polling intervals

- Device status polling is configured in `custom_components/marstek/coordinator.py` (currently `SCAN_INTERVAL = 10s`).
- The IP-change scanner runs separately (`custom_components/marstek/scanner.py`, `SCAN_INTERVAL = 60s`).

## Quality and style expectations

- Follow Home Assistant coordinator patterns.
- Keep changes minimal and consistent with existing style.
- Prefer clear user-facing error messages in config flows via `strings.json` / translations.
- Integration-grade hygiene: avoid per-entity I/O, keep one coordinator per device, debounce refreshes, and ensure options changes trigger reloads.
- Testing/QA: prefer pytest + `pytest-homeassistant-custom-component`; keep manifest versions pinned and metadata valid for HACS/hassfest.

## Testing and QA expectations

- Aim for Bronze+ quality scale: 100% config_flow coverage, connection tested in setup, unload/reload covered.
- Test structure: `tests/` mirrors platforms (`test_config_flow.py`, `test_init.py`, `test_sensor.py`, etc.) with shared fixtures in `tests/conftest.py` (enable custom integrations).
- Use `pytest-homeassistant-custom-component` with pinned versions in `requirements_test.txt`; mock UDP/HTTP I/O—no live devices.
- Cover failures: cannot_connect, invalid_auth/invalid_discovery_info, already_configured, coordinator timeouts, action retries.
- Mark coordinator failures with `UpdateFailed` to surface entity unavailability; snapshot diagnostics if added later.
- CI: run hassfest + lint (ruff/mypy) + pytest (coverage threshold) on latest supported Python versions.

## Local development

- Run Home Assistant dev instance and watch logs for the `marstek` logger.
- When troubleshooting discovery: ensure devices and HA are on the same LAN segment and UDP port is reachable.
