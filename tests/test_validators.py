"""Tests for pymarstek validators module."""

from __future__ import annotations

import pytest

from custom_components.marstek.pymarstek.validators import (
    MAX_DEVICE_ID,
    MAX_POWER_VALUE,
    MAX_TIME_SLOTS,
    MAX_WEEK_SET,
    VALID_METHODS,
    VALID_MODES,
    ValidationError,
    validate_command,
    validate_device_id,
    validate_es_set_mode_config,
    validate_json_message,
    validate_manual_config,
    validate_method,
    validate_params,
    validate_passive_config,
    validate_power_value,
    validate_time_format,
    validate_week_set,
)


class TestValidateTimeFormat:
    """Tests for validate_time_format."""

    @pytest.mark.parametrize("time_str", [
        "00:00",
        "12:30",
        "23:59",
        "9:05",
        "09:05",
    ])
    def test_valid_times(self, time_str: str) -> None:
        """Test valid time formats are accepted."""
        validate_time_format(time_str)  # Should not raise

    @pytest.mark.parametrize("time_str", [
        "24:00",
        "12:60",
        "invalid",
        "",
        "12",
        "12:30:00",  # Seconds not allowed
    ])
    def test_invalid_times(self, time_str: str) -> None:
        """Test invalid time formats are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_time_format(time_str)
        assert exc_info.value.field == "time"

    def test_non_string_rejected(self) -> None:
        """Test non-string types are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_time_format(1230)  # type: ignore[arg-type]
        assert "must be a string" in exc_info.value.message


class TestValidateDeviceId:
    """Tests for validate_device_id."""

    @pytest.mark.parametrize("device_id", [0, 1, 127, 255])
    def test_valid_device_ids(self, device_id: int) -> None:
        """Test valid device IDs are accepted."""
        validate_device_id(device_id)  # Should not raise

    def test_negative_id_rejected(self) -> None:
        """Test negative device ID is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_device_id(-1)
        assert exc_info.value.field == "id"
        assert f"0 and {MAX_DEVICE_ID}" in exc_info.value.message

    def test_too_large_id_rejected(self) -> None:
        """Test device ID > 255 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_device_id(256)
        assert exc_info.value.field == "id"

    def test_non_integer_rejected(self) -> None:
        """Test non-integer device ID is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_device_id("0")  # type: ignore[arg-type]
        assert "must be an integer" in exc_info.value.message


class TestValidatePowerValue:
    """Tests for validate_power_value."""

    @pytest.mark.parametrize("power", [
        0,
        1000,
        -1000,
        MAX_POWER_VALUE,
        -MAX_POWER_VALUE,
    ])
    def test_valid_power_values(self, power: int) -> None:
        """Test valid power values are accepted."""
        validate_power_value(power)  # Should not raise

    def test_power_too_high_rejected(self) -> None:
        """Test power exceeding max is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_power_value(MAX_POWER_VALUE + 1)
        assert exc_info.value.field == "power"
        assert f"-{MAX_POWER_VALUE} and {MAX_POWER_VALUE}" in exc_info.value.message

    def test_power_too_low_rejected(self) -> None:
        """Test power below negative max is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_power_value(-MAX_POWER_VALUE - 1)
        assert exc_info.value.field == "power"

    def test_non_integer_rejected(self) -> None:
        """Test non-integer power is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_power_value(1000.5)  # type: ignore[arg-type]
        assert "must be an integer" in exc_info.value.message


class TestValidateWeekSet:
    """Tests for validate_week_set."""

    @pytest.mark.parametrize("week_set", [0, 1, 63, 127])
    def test_valid_week_sets(self, week_set: int) -> None:
        """Test valid week_set values are accepted."""
        validate_week_set(week_set)  # Should not raise

    def test_negative_week_set_rejected(self) -> None:
        """Test negative week_set is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_week_set(-1)
        assert exc_info.value.field == "week_set"

    def test_too_large_week_set_rejected(self) -> None:
        """Test week_set > 127 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_week_set(128)
        assert f"0 and {MAX_WEEK_SET}" in exc_info.value.message


class TestValidateManualConfig:
    """Tests for validate_manual_config."""

    @pytest.fixture
    def valid_manual_config(self) -> dict:
        """Return a valid manual configuration."""
        return {
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,
            "power": 1000,
            "enable": 1,
        }

    def test_valid_config(self, valid_manual_config: dict) -> None:
        """Test valid manual config is accepted."""
        validate_manual_config(valid_manual_config)  # Should not raise

    def test_missing_required_field(self, valid_manual_config: dict) -> None:
        """Test missing required field is rejected."""
        del valid_manual_config["power"]
        with pytest.raises(ValidationError) as exc_info:
            validate_manual_config(valid_manual_config)
        assert "missing required fields" in exc_info.value.message
        assert "power" in exc_info.value.message

    def test_invalid_time_num(self, valid_manual_config: dict) -> None:
        """Test invalid time_num is rejected."""
        valid_manual_config["time_num"] = MAX_TIME_SLOTS
        with pytest.raises(ValidationError) as exc_info:
            validate_manual_config(valid_manual_config)
        assert "time_num" in exc_info.value.field

    def test_invalid_enable_value(self, valid_manual_config: dict) -> None:
        """Test enable must be 0 or 1."""
        valid_manual_config["enable"] = 2
        with pytest.raises(ValidationError) as exc_info:
            validate_manual_config(valid_manual_config)
        assert exc_info.value.field == "enable"


class TestValidatePassiveConfig:
    """Tests for validate_passive_config."""

    @pytest.fixture
    def valid_passive_config(self) -> dict:
        """Return a valid passive configuration."""
        return {
            "power": 1000,
            "cd_time": 3600,
        }

    def test_valid_config(self, valid_passive_config: dict) -> None:
        """Test valid passive config is accepted."""
        validate_passive_config(valid_passive_config)  # Should not raise

    def test_missing_cd_time(self, valid_passive_config: dict) -> None:
        """Test missing cd_time is rejected."""
        del valid_passive_config["cd_time"]
        with pytest.raises(ValidationError) as exc_info:
            validate_passive_config(valid_passive_config)
        assert "cd_time" in exc_info.value.message

    def test_cd_time_too_large(self, valid_passive_config: dict) -> None:
        """Test cd_time > 24 hours is rejected."""
        valid_passive_config["cd_time"] = 86401
        with pytest.raises(ValidationError) as exc_info:
            validate_passive_config(valid_passive_config)
        assert "cd_time" in exc_info.value.field


class TestValidateEsSetModeConfig:
    """Tests for validate_es_set_mode_config."""

    def test_auto_mode_no_extra_config(self) -> None:
        """Test Auto mode doesn't require extra config."""
        config = {"mode": "Auto"}
        validate_es_set_mode_config(config)  # Should not raise

    def test_ai_mode_no_extra_config(self) -> None:
        """Test AI mode doesn't require extra config."""
        config = {"mode": "AI"}
        validate_es_set_mode_config(config)  # Should not raise

    def test_manual_mode_requires_config(self) -> None:
        """Test Manual mode requires manual_cfg."""
        config = {"mode": "Manual"}
        with pytest.raises(ValidationError) as exc_info:
            validate_es_set_mode_config(config)
        assert "manual_cfg is required" in exc_info.value.message

    def test_passive_mode_requires_config(self) -> None:
        """Test Passive mode requires passive_cfg."""
        config = {"mode": "Passive"}
        with pytest.raises(ValidationError) as exc_info:
            validate_es_set_mode_config(config)
        assert "passive_cfg is required" in exc_info.value.message

    def test_invalid_mode_rejected(self) -> None:
        """Test invalid mode is rejected."""
        config = {"mode": "Invalid"}
        with pytest.raises(ValidationError) as exc_info:
            validate_es_set_mode_config(config)
        assert exc_info.value.field == "mode"
        # Check all valid modes are mentioned
        for mode in VALID_MODES:
            assert mode in exc_info.value.message


class TestValidateMethod:
    """Tests for validate_method."""

    @pytest.mark.parametrize("method", list(VALID_METHODS.keys()))
    def test_all_valid_methods(self, method: str) -> None:
        """Test all defined methods are accepted."""
        spec = validate_method(method)
        assert spec.method == method

    def test_unknown_method_rejected(self) -> None:
        """Test unknown method is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_method("Unknown.Method")
        assert "Unknown method" in exc_info.value.message
        assert exc_info.value.field == "method"

    def test_non_string_rejected(self) -> None:
        """Test non-string method is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_method(123)  # type: ignore[arg-type]
        assert "must be a string" in exc_info.value.message


class TestValidateParams:
    """Tests for validate_params."""

    def test_valid_get_status_params(self) -> None:
        """Test valid ES.GetStatus params are accepted."""
        validate_params("ES.GetStatus", {"id": 0})  # Should not raise

    def test_missing_required_param(self) -> None:
        """Test missing required params are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_params("ES.SetMode", {"id": 0})  # Missing config
        assert "Missing required parameters" in exc_info.value.message
        assert "config" in exc_info.value.message

    def test_unknown_param_rejected(self) -> None:
        """Test unknown params are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_params("ES.GetStatus", {"id": 0, "unknown": "value"})
        assert "Unknown parameters" in exc_info.value.message

    def test_invalid_device_id_in_params(self) -> None:
        """Test invalid device ID in params is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_params("ES.GetStatus", {"id": 999})
        assert exc_info.value.field == "id"


class TestValidateCommand:
    """Tests for validate_command."""

    def test_valid_command(self) -> None:
        """Test valid command structure is accepted."""
        command = {
            "id": 1,
            "method": "ES.GetStatus",
            "params": {"id": 0},
        }
        validate_command(command)  # Should not raise

    def test_missing_id(self) -> None:
        """Test missing command id is rejected."""
        command = {
            "method": "ES.GetStatus",
            "params": {},
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_command(command)
        assert "missing required field 'id'" in exc_info.value.message

    def test_missing_method(self) -> None:
        """Test missing method is rejected."""
        command = {
            "id": 1,
            "params": {},
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_command(command)
        assert "missing required field 'method'" in exc_info.value.message

    def test_negative_command_id_rejected(self) -> None:
        """Test negative command id is rejected."""
        command = {
            "id": -1,
            "method": "ES.GetStatus",
            "params": {},
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_command(command)
        assert "non-negative integer" in exc_info.value.message


class TestValidateJsonMessage:
    """Tests for validate_json_message."""

    def test_valid_json_message(self) -> None:
        """Test valid JSON message is parsed and validated."""
        message = '{"id": 1, "method": "ES.GetStatus", "params": {"id": 0}}'
        result = validate_json_message(message)
        assert result["id"] == 1
        assert result["method"] == "ES.GetStatus"

    def test_invalid_json_rejected(self) -> None:
        """Test invalid JSON is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_json_message("not valid json")
        assert "Invalid JSON" in exc_info.value.message

    def test_empty_message_rejected(self) -> None:
        """Test empty message is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_json_message("")
        assert "cannot be empty" in exc_info.value.message

    def test_whitespace_only_rejected(self) -> None:
        """Test whitespace-only message is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_json_message("   ")
        assert "cannot be empty" in exc_info.value.message

    def test_non_string_rejected(self) -> None:
        """Test non-string message is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            validate_json_message({"id": 1})  # type: ignore[arg-type]
        assert "must be a string" in exc_info.value.message


class TestValidateSetModeCommand:
    """Tests for complete ES.SetMode command validation."""

    def test_valid_manual_charge_command(self) -> None:
        """Test valid manual charge command is accepted."""
        command = {
            "id": 1,
            "method": "ES.SetMode",
            "params": {
                "id": 0,
                "config": {
                    "mode": "Manual",
                    "manual_cfg": {
                        "time_num": 0,
                        "start_time": "00:00",
                        "end_time": "23:59",
                        "week_set": 127,
                        "power": -1300,
                        "enable": 1,
                    },
                },
            },
        }
        validate_command(command)  # Should not raise

    def test_valid_passive_mode_command(self) -> None:
        """Test valid passive mode command is accepted."""
        command = {
            "id": 1,
            "method": "ES.SetMode",
            "params": {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {
                        "power": 1000,
                        "cd_time": 3600,
                    },
                },
            },
        }
        validate_command(command)  # Should not raise

    def test_manual_mode_invalid_power(self) -> None:
        """Test manual mode with invalid power is rejected."""
        command = {
            "id": 1,
            "method": "ES.SetMode",
            "params": {
                "id": 0,
                "config": {
                    "mode": "Manual",
                    "manual_cfg": {
                        "time_num": 0,
                        "start_time": "00:00",
                        "end_time": "23:59",
                        "week_set": 127,
                        "power": 999999,  # Way too high
                        "enable": 1,
                    },
                },
            },
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_command(command)
        assert "power" in exc_info.value.field


class TestValidationErrorAttributes:
    """Tests for ValidationError exception attributes."""

    def test_error_has_message_and_field(self) -> None:
        """Test ValidationError has message and field attributes."""
        error = ValidationError("Test error", "test_field")
        assert error.message == "Test error"
        assert error.field == "test_field"
        assert str(error) == "Test error"

    def test_error_field_optional(self) -> None:
        """Test ValidationError field is optional."""
        error = ValidationError("Test error")
        assert error.message == "Test error"
        assert error.field is None
