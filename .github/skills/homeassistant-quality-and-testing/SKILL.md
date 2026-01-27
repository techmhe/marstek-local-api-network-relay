---
name: homeassistant-quality-and-testing
description: High-level Home Assistant integration best practices, quality scale cues, and testing/CI expectations for custom components
---

# Home Assistant Quality & Testing

Use this skill to align changes with Home Assistant best practices and the Integration Quality Scale expectations.

## When to Use
- Planning or reviewing changes for config flows, options, or reauth
- Deciding how to structure polling, discovery, and entities
- Ensuring translations, metadata, and versioning are correct
- Setting up or updating tests and CI
 - Driving toward Bronze/Silver IQS targets (config flow coverage, >95% overall coverage, diagnostics)

## Architectural Principles
- **Async-only**: Never block the event loop; offload sync work via `hass.async_add_executor_job`.
- **Coordinator-first**: Centralize device I/O in `DataUpdateCoordinator`; entities consume `coordinator.data`.
- **Single source of discovery**: Rely on declared discovery (dhcp/zeroconf/ssdp) or dedicated scanner; avoid ad-hoc discovery inside polling.
- **Separation**: Keep protocol/library logic outside entities; prefer a library (`requirements`) for raw API/UDP/HTTP handling.
- **Quality Scale focus**: Bronze requires 100% config_flow coverage and connection tests; Silver pushes >95% overall coverage, strict typing, and reauth flows.

## Config / Options / Reauth Patterns
- **UI-first**: No new YAML; all setup via `config_flow.py` with selectors where helpful.
- **Duplicate avoidance**: Abort if a device is already configured; update IP/host on existing entries when discovery reports changes.
- **Options reload**: Register `entry.add_update_listener` to reload on options change.
- **Reauth**: Trigger `entry.async_start_reauth`; ask only for the changed credential and update the existing entry.
 - **Duplicate enforcement**: Set `unique_id` early and call `_abort_if_unique_id_configured()` for user/discovery steps.

## Entities & Registries
- Set `_attr_has_entity_name = True`; names should be capability-only (device name is prepended by HA).
- Provide `device_info` with stable identifiers (prefer MAC/serial over IP); all entities for a device must share the same identifiers set.
- Keep `unique_id` stable and predictable (e.g., `{ble_mac}_{key}`); changing it breaks history and customizations.
- Only create entities for data that actually exists to avoid permanent `unavailable` noise.

## Entity Best Practices
- Use constants from `homeassistant.const` for units:
  - `UnitOfEnergy.WATT_HOUR` not `"Wh"`
  - `UnitOfPower.WATT` not `"W"`
  - `UnitOfTemperature.CELSIUS` not `"°C"`
- Use device classes from `homeassistant.components.sensor`:
  - `SensorDeviceClass.BATTERY` for battery level sensors
  - `SensorDeviceClass.POWER` for power sensors
  - `SensorDeviceClass.ENERGY` for energy sensors
  - `SensorDeviceClass.TEMPERATURE` for temperature sensors
- Use state classes appropriately:
  - `SensorStateClass.MEASUREMENT` for instantaneous values (power, temperature)
  - `SensorStateClass.TOTAL_INCREASING` for cumulative energy counters
- Use `EntityCategory.DIAGNOSTIC` for non-primary sensors (WiFi RSSI, temperatures)

## Diagnostics (Gold Quality Scale)
- Create `diagnostics.py` with `async_get_config_entry_diagnostics` function
- Return a dict with: entry data, device_info, coordinator_data, last_update_success, last_exception
- Redact sensitive data before returning:
  - IPs, MACs, SSIDs, tokens, passwords
  - Use a `TO_REDACT` list pattern for consistency:
    ```python
    TO_REDACT = {"host", "ip", "mac", "ble_mac", "wifi_mac", "wifi_name", "SSID", "bleMac"}
    
    def _redact_dict(data: dict) -> dict:
        return {k: "**REDACTED**" if k in TO_REDACT else v for k, v in data.items()}
    ```
- Test diagnostics with snapshot tests and verify redaction

## Manifest & Metadata
- Pin requirements (e.g., `pymarstek==x.y.z`) to avoid breaking upgrades.
- Set `version`, `config_flow: true`, `iot_class`, and `codeowners`; keep documentation and issue tracker URLs current.
- For HACS, keep releases/tagging consistent and add `hacs.json` if distribution via HACS.

## Translations
- Author strings in `strings.json`; mirror to `translations/en.json`.
- Use descriptive error keys (`cannot_connect`, `invalid_auth`, `already_configured`).
- Prefer placeholders for dynamic content (e.g., `{ip_address}`) to keep translations flexible.

## Testing & CI
- Use `pytest` with `pytest-homeassistant-custom-component`; pin test deps in `requirements_test.txt`.
- Test layout: `tests/` mirrors component files (`test_config_flow.py`, `test_init.py`, `test_sensor.py`, etc.); put shared fixtures in `tests/conftest.py` (enable custom integrations).
- Config flow: cover success + cannot_connect + invalid_auth/invalid_discovery_info + already_configured; assert unique_id and aborts.
- Coordinator/entities: mock transport; assert happy path + errors raise `UpdateFailed` and surface unavailable states; gate entities on data keys.
- Actions/commands: verify polling is paused, retries fire, verification logic works, and failures bubble.
- Snapshot/diagnostics (Gold path): use `syrupy` HA extension for diagnostics/device registry dumps; redact sensitive fields.
- CI: hassfest + lint (ruff, mypy optional) + pytest with coverage threshold (e.g., `--cov-fail-under=95`); test latest supported Python versions.

## Operational Hygiene
- Debounce manual refreshes with `coordinator.async_request_refresh()`.
- Pause polling when sending control commands that reuse the same transport to avoid concurrent traffic.
- Log warnings/errors with actionable context (host, method) but avoid noisy debug logs by default.

## Quick Checklist
- [ ] No blocking I/O on the event loop
- [ ] Coordinator is the sole reader/writer to the device
- [ ] Config/Options/Reauth flows implemented and reload on options change
- [ ] Stable unique IDs + device identifiers
- [ ] Translations updated (strings + en.json)
- [ ] Requirements pinned; manifest fields valid; hassfest/HACS clean
- [ ] Tests cover config flow, coordinator happy-path and failure, and entity states
