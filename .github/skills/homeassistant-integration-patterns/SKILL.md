---
name: homeassistant-integration-patterns
description: Project-specific patterns for the Marstek integration (config flow, coordinator, scanner, entities, translations)
---

# Home Assistant Integration Patterns (Marstek)

This skill helps you make correct, repo-consistent changes to this Home Assistant custom integration.

## When to Use

- Adding/changing sensors
- Changing discovery/config flow behavior
- Updating coordinator error handling
- Working on translations or diagnostics
- Ensuring changes meet Home Assistant integration quality expectations

## Quick Map

| Task | File(s) |
|---|---|
| Setup / teardown / coordinator wiring | `custom_components/marstek/__init__.py` |
| Config flow (user, dhcp, integration discovery) | `custom_components/marstek/config_flow.py` |
| Central polling | `custom_components/marstek/coordinator.py` |
| IP-change scanner | `custom_components/marstek/scanner.py` |
| Entities (sensors) | `custom_components/marstek/sensor.py` |
| Device automation actions | `custom_components/marstek/device_action.py` |
| Text / translations | `custom_components/marstek/strings.json`, `custom_components/marstek/translations/en.json` |
| Local API reference | `docs/MarstekDeviceOpenApi.pdf` |

## Core Rules

1. **Coordinator-only I/O**
   - Never add per-entity UDP calls.
   - Read everything from `MarstekDataUpdateCoordinator.data`.

2. **Async-only**
   - Only do async I/O; never block the event loop.

3. **Avoid unavailable clutter**
   - Only create entities when there’s a corresponding data key in coordinator output.
   - Prefer explicit per-sensor classes or a description table keyed by coordinator data.

4. **Use translation-aware config-flow errors**
   - Config flow errors should use keys defined in `custom_components/marstek/strings.json`.
   - Reauth flows should ask only for the changed credential and update the existing entry.

5. **Stable identifiers**
   - Use BLE-MAC-based unique IDs for entities and devices; never pivot on IPs.
   - Keep `_attr_has_entity_name = True` and set `device_info` for grouping.

## Adding a new sensor

Steps:
1. Find the value on `coordinator.data` (a plain `dict[str, Any]` coming from `pymarstek`).
2. Add a new sensor entity in `custom_components/marstek/sensor.py`.
3. Keep the `unique_id` stable (BLE-MAC based + sensor key).
4. If user-facing, add translation in `custom_components/marstek/translations/en.json` (and keep `strings.json` in sync).
5. Only register entities for data keys that exist to avoid permanent `unavailable` noise.

## Common pitfalls

- Polling/discovery storms (too many UDP requests too frequently).
- Doing IP discovery inside setup or coordinator updates (scanner already handles this).
- Sending control commands without pausing polling (causes concurrent UDP traffic and flaky results).
- Breaking unique IDs (must remain stable across upgrades and IP changes).
- Skipping options reload listeners or reauth handling in `config_flow.py`.
