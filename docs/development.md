# Development

## Repo layout

- `custom_components/marstek/` — integration
- `custom_components/marstek/pymarstek/` — UDP client
- `tools/mock_device/` — mock device for local testing
- `docs/marstek_device_openapi.MD` — protocol reference

## Running tests

From repo root:

```
# Linting
python3 -m ruff check custom_components/marstek/

# Type checking
python3 -m mypy --strict custom_components/marstek/

# Tests with coverage
pytest tests/ -q --cov=custom_components/marstek --cov-fail-under=95
```

## Mock device

Run the mock device to develop without hardware:

```
cd tools
python -m mock_device
```

Backwards-compatible shim (still works):

```
python tools/mock_device/mock_marstek.py
```

## Protocol reference

See `docs/marstek_device_openapi.MD`.
