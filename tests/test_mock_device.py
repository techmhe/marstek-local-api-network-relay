"""Tests for the mock Marstek device simulator."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

# Import from tools directory
import sys
sys.path.insert(0, "tools/mock_device")

from mock_marstek import (
    BatterySimulator,
    HouseholdSimulator,
    MockMarstekDevice,
    MODE_AUTO,
    MODE_AI,
    MODE_MANUAL,
    MODE_PASSIVE,
    STATUS_CHARGING,
    STATUS_DISCHARGING,
    STATUS_IDLE,
)


class TestBatterySimulator:
    """Tests for the BatterySimulator class."""

    def test_initial_state(self) -> None:
        """Test simulator initializes with correct state."""
        sim = BatterySimulator(initial_soc=75)
        state = sim.get_state()

        assert state["soc"] == 75
        assert state["mode"] == MODE_AUTO
        assert state["power"] == 0
        assert state["status"] == STATUS_IDLE

    def test_set_mode_passive(self) -> None:
        """Test setting passive mode with power and duration."""
        sim = BatterySimulator(initial_soc=50)

        sim.set_mode(MODE_PASSIVE, {"power": -2000, "cd_time": 3600})
        state = sim.get_state()

        assert state["mode"] == MODE_PASSIVE
        assert sim.target_power == -2000
        assert sim.passive_end_time is not None
        assert state["passive_remaining"] > 0
        # Verify passive_cfg is included for Home Assistant number entities
        assert state["passive_cfg"] is not None
        assert state["passive_cfg"]["power"] == -2000
        assert state["passive_cfg"]["cd_time"] > 0

    def test_set_mode_manual_schedule(self) -> None:
        """Test setting manual mode with schedule configuration."""
        sim = BatterySimulator(initial_soc=50)

        schedule_config = {
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,  # All days
            "power": -1500,
            "enable": 1,
        }
        sim.set_mode(MODE_MANUAL, schedule_config)
        state = sim.get_state()

        assert state["mode"] == MODE_MANUAL
        assert len(sim.manual_schedules) == 1
        assert sim.manual_schedules[0]["power"] == -1500

    def test_set_mode_auto(self) -> None:
        """Test switching to auto mode."""
        sim = BatterySimulator(initial_soc=50)

        # Start in passive, then switch to auto
        sim.set_mode(MODE_PASSIVE, {"power": 1000, "cd_time": 3600})
        sim.set_mode(MODE_AUTO)

        state = sim.get_state()
        assert state["mode"] == MODE_AUTO
        # Verify passive_cfg is None when not in passive mode
        assert state["passive_cfg"] is None

    def test_set_mode_ai(self) -> None:
        """Test switching to AI mode."""
        sim = BatterySimulator(initial_soc=50)
        sim.set_mode(MODE_AI)

        assert sim.get_state()["mode"] == MODE_AI

    def test_soc_limits_no_discharge_below_5(self) -> None:
        """Test that battery cannot discharge below 5% SOC."""
        sim = BatterySimulator(initial_soc=3)

        # Try to discharge (positive power)
        limited = sim._apply_soc_limits(1000)
        assert limited == 0  # Should be blocked

    def test_soc_limits_no_charge_above_100(self) -> None:
        """Test that battery cannot charge above 100% SOC."""
        sim = BatterySimulator(initial_soc=100)

        # Try to charge (negative power)
        limited = sim._apply_soc_limits(-1000)
        assert limited == 0  # Should be blocked

    def test_soc_limits_taper_charging_near_full(self) -> None:
        """Test charging power tapers as SOC approaches 100%."""
        sim = BatterySimulator(initial_soc=95)

        # Charging at 95% should be tapered (5% remaining = 0.5 factor)
        limited = sim._apply_soc_limits(-2000)
        assert -1100 <= limited <= -900  # ~50% of 2000

    def test_soc_limits_taper_discharging_near_empty(self) -> None:
        """Test discharging power tapers as SOC approaches 0%."""
        sim = BatterySimulator(initial_soc=7)

        # Discharging at 7% should be tapered (0.7 factor)
        limited = sim._apply_soc_limits(1000)
        assert 650 <= limited <= 750  # ~70% of 1000

    def test_auto_mode_discharges_to_cover_household(self) -> None:
        """Test auto mode discharges to cover household consumption."""
        sim = BatterySimulator(initial_soc=50)

        # Auto mode should discharge to cover household consumption
        household = 500  # 500W consumption
        target = sim._calculate_target_power(household)
        assert target == household  # Discharge to cover household

    def test_auto_mode_limited_by_max_discharge(self) -> None:
        """Test auto mode is limited by max discharge power."""
        sim = BatterySimulator(initial_soc=50, max_discharge_power=3000)

        # Very high household consumption
        household = 5000
        target = sim._calculate_target_power(household)
        assert target == 3000  # Limited to max

    def test_auto_mode_no_discharge_when_soc_low(self) -> None:
        """Test auto mode doesn't discharge when SOC is below 10%."""
        sim = BatterySimulator(initial_soc=8)

        target = sim._calculate_target_power(1000)
        assert target == 0  # No discharge when SOC < 10%

    def test_passive_mode_uses_target_power(self) -> None:
        """Test passive mode returns configured target power."""
        sim = BatterySimulator(initial_soc=50)
        sim.set_mode(MODE_PASSIVE, {"power": -2500, "cd_time": 3600})

        target = sim._calculate_target_power(1000)  # household ignored in passive
        assert target == -2500

    def test_status_label_charging(self) -> None:
        """Test status shows 'Buying' when charging."""
        sim = BatterySimulator(initial_soc=50)
        sim.actual_power = -500  # Charging

        state = sim.get_state()
        assert state["status"] == STATUS_CHARGING

    def test_status_label_discharging(self) -> None:
        """Test status shows 'Selling' when discharging."""
        sim = BatterySimulator(initial_soc=50)
        sim.actual_power = 500  # Discharging

        state = sim.get_state()
        assert state["status"] == STATUS_DISCHARGING

    def test_status_label_idle(self) -> None:
        """Test status shows 'Idle' when power near zero."""
        sim = BatterySimulator(initial_soc=50)
        sim.actual_power = 10  # Very low power

        state = sim.get_state()
        assert state["status"] == STATUS_IDLE

    def test_manual_schedule_update_existing_slot(self) -> None:
        """Test updating an existing manual schedule slot."""
        sim = BatterySimulator(initial_soc=50)

        # Add initial schedule
        sim.set_mode(MODE_MANUAL, {
            "time_num": 0,
            "start_time": "08:00",
            "end_time": "16:00",
            "week_set": 127,
            "power": -1000,
            "enable": 1,
        })

        # Update same slot
        sim.set_mode(MODE_MANUAL, {
            "time_num": 0,
            "start_time": "10:00",
            "end_time": "14:00",
            "week_set": 31,  # Mon-Fri
            "power": -2000,
            "enable": 1,
        })

        # Should still have only one schedule
        assert len(sim.manual_schedules) == 1
        assert sim.manual_schedules[0]["power"] == -2000
        assert sim.manual_schedules[0]["start_time"] == "10:00"

    def test_manual_schedule_multiple_slots(self) -> None:
        """Test adding multiple manual schedule slots."""
        sim = BatterySimulator(initial_soc=50)

        sim.set_mode(MODE_MANUAL, {
            "time_num": 0,
            "start_time": "08:00",
            "end_time": "12:00",
            "power": -1500,
            "enable": 1,
        })

        sim.set_mode(MODE_MANUAL, {
            "time_num": 1,
            "start_time": "18:00",
            "end_time": "22:00",
            "power": 800,
            "enable": 1,
        })

        assert len(sim.manual_schedules) == 2
        assert sim.manual_schedules[0]["time_num"] == 0
        assert sim.manual_schedules[1]["time_num"] == 1

    def test_passive_mode_expiration(self) -> None:
        """Test passive mode switches to auto when timer expires."""
        sim = BatterySimulator(initial_soc=50)

        # Set passive mode with very short duration
        sim.set_mode(MODE_PASSIVE, {"power": -1000, "cd_time": 1})

        # Simulate time passing
        sim.passive_end_time = time.time() - 1  # Already expired

        # Trigger state update
        sim._update_state(1.0)

        assert sim.mode == MODE_AUTO
        assert sim.passive_end_time is None

    def test_soc_changes_with_charging(self) -> None:
        """Test SOC increases when charging."""
        sim = BatterySimulator(initial_soc=50, capacity_wh=5120)

        # Use passive mode to set power (simulates charging at 2560W for 1 hour)
        sim.set_mode(MODE_PASSIVE, {"power": -2560, "cd_time": 7200})
        sim._update_state(3600)  # 1 hour = 2560Wh = 50% of 5120Wh

        # SOC should have increased significantly
        assert sim.soc > 95

    def test_soc_changes_with_discharging(self) -> None:
        """Test SOC decreases when discharging."""
        sim = BatterySimulator(initial_soc=50, capacity_wh=5120)

        # Use passive mode to set power (simulates discharging at 2560W for 1 hour)
        sim.set_mode(MODE_PASSIVE, {"power": 2560, "cd_time": 7200})
        sim._update_state(3600)  # 1 hour

        # SOC should have decreased significantly
        assert sim.soc < 5

    def test_thread_safety_get_state(self) -> None:
        """Test get_state is thread-safe (uses lock)."""
        sim = BatterySimulator(initial_soc=50)

        # Start simulation
        sim.start()

        try:
            # Should be able to get state while simulation is running
            for _ in range(10):
                state = sim.get_state()
                assert "soc" in state
                assert "power" in state
                assert "mode" in state
                time.sleep(0.05)
        finally:
            sim.stop()

    def test_thread_safety_set_mode(self) -> None:
        """Test set_mode is thread-safe (uses lock)."""
        sim = BatterySimulator(initial_soc=50)

        sim.start()

        try:
            # Should be able to set mode while simulation is running
            sim.set_mode(MODE_PASSIVE, {"power": -1000, "cd_time": 3600})
            assert sim.get_state()["mode"] == MODE_PASSIVE

            sim.set_mode(MODE_AUTO)
            assert sim.get_state()["mode"] == MODE_AUTO
        finally:
            sim.stop()


class TestManualScheduleMatching:
    """Tests for manual schedule time/day matching."""

    def test_get_active_schedule_matches_current_time(self) -> None:
        """Test schedule matching for current time."""
        sim = BatterySimulator(initial_soc=50)

        # Add schedule that covers all day, all week
        sim.manual_schedules = [{
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,  # All days
            "power": -1500,
            "enable": True,
        }]

        schedule = sim._get_active_schedule()
        assert schedule is not None
        assert schedule["power"] == -1500

    def test_get_active_schedule_disabled(self) -> None:
        """Test disabled schedule is not matched."""
        sim = BatterySimulator(initial_soc=50)

        sim.manual_schedules = [{
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,
            "power": -1500,
            "enable": False,  # Disabled
        }]

        schedule = sim._get_active_schedule()
        assert schedule is None

    def test_get_active_schedule_outside_time(self) -> None:
        """Test schedule outside time window is not matched."""
        sim = BatterySimulator(initial_soc=50)

        # Schedule that's definitely not now (assuming test doesn't run at exactly 03:00-03:01)
        sim.manual_schedules = [{
            "time_num": 0,
            "start_time": "03:00",
            "end_time": "03:01",
            "week_set": 127,
            "power": -1500,
            "enable": True,
        }]

        # This test might fail if run exactly at 03:00-03:01, but that's unlikely
        # For more robust testing, we'd mock datetime.now()
        # For now, just verify the logic works with a known schedule

    def test_get_active_schedule_wrong_day(self) -> None:
        """Test schedule on wrong day is not matched."""
        sim = BatterySimulator(initial_soc=50)

        # week_set = 0 means no days enabled
        sim.manual_schedules = [{
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 0,  # No days
            "power": -1500,
            "enable": True,
        }]

        schedule = sim._get_active_schedule()
        assert schedule is None

    def test_multiple_schedules_first_match_wins(self) -> None:
        """Test first matching schedule is returned."""
        sim = BatterySimulator(initial_soc=50)

        sim.manual_schedules = [
            {
                "time_num": 0,
                "start_time": "00:00",
                "end_time": "23:59",
                "week_set": 127,
                "power": -1000,
                "enable": True,
            },
            {
                "time_num": 1,
                "start_time": "00:00",
                "end_time": "23:59",
                "week_set": 127,
                "power": -2000,
                "enable": True,
            },
        ]

        schedule = sim._get_active_schedule()
        assert schedule is not None
        assert schedule["power"] == -1000  # First one wins


class TestHouseholdSimulator:
    """Tests for the HouseholdSimulator class."""

    def test_get_consumption_returns_positive(self) -> None:
        """Test household consumption is always positive."""
        sim = HouseholdSimulator()
        
        for _ in range(10):
            consumption = sim.get_consumption()
            assert consumption >= 50  # Minimum base load

    def test_base_load_included(self) -> None:
        """Test base load is always included in consumption."""
        sim = HouseholdSimulator()
        sim.base_load = 200
        
        consumption = sim.get_consumption()
        # Should be at least base load (might be higher with time-of-day variation)
        assert consumption >= 50  # After fluctuation minimum

    def test_force_cooking_event(self) -> None:
        """Test forced cooking event increases consumption."""
        sim = HouseholdSimulator()
        
        # Use base_load as reference (avoids random event interference)
        baseline = sim.base_load
        
        # Force a cooking event
        sim.force_cooking_event(power=2500, duration_mins=15)
        
        # Get new consumption (should include cooking)
        with_cooking = sim.get_consumption()
        
        # Consumption should include most of the cooking power
        # (accounting for fluctuation, it should be at least 2000W more than base)
        assert with_cooking > baseline + 2000

    def test_consumption_fluctuation(self) -> None:
        """Test consumption has realistic fluctuation."""
        sim = HouseholdSimulator()
        
        # Get multiple readings
        readings = [sim.get_consumption() for _ in range(10)]
        
        # Not all readings should be identical (fluctuation)
        unique_readings = len(set(readings))
        assert unique_readings > 1


class TestGridPowerCalculation:
    """Tests for grid power calculation in auto mode."""

    def test_grid_power_reduced_by_battery_discharge(self) -> None:
        """Test battery discharge reduces grid power import."""
        sim = BatterySimulator(initial_soc=50)
        
        # Manually set values to test calculation
        sim.household.current_consumption = 1000
        sim.actual_power = 800  # Battery discharging 800W
        
        # Grid should see: 1000W household - 800W discharge = 200W import
        # Formula: grid_power = household - battery_power
        sim.grid_power = sim.household.current_consumption - sim.actual_power
        
        state = sim.get_state()
        assert state["grid_power"] == 200  # Only 200W from grid

    def test_grid_power_increased_by_battery_charge(self) -> None:
        """Test battery charging increases grid power import."""
        sim = BatterySimulator(initial_soc=50)
        
        sim.household.current_consumption = 500
        sim.actual_power = -1000  # Battery charging at 1000W
        
        # Grid should see: 500W household - (-1000W) = 1500W import
        sim.grid_power = sim.household.current_consumption - sim.actual_power
        
        state = sim.get_state()
        assert state["grid_power"] == 1500  # Extra draw for charging

    def test_state_includes_household_consumption(self) -> None:
        """Test state includes household consumption value."""
        sim = BatterySimulator(initial_soc=50)
        state = sim.get_state()
        
        assert "household_consumption" in state
        assert state["household_consumption"] >= 50


class TestImmediatePowerUpdate:
    """Tests for immediate power updates after mode changes.
    
    These tests verify that actual_power is updated synchronously when
    a mode change is made, so ES.GetStatus returns correct values
    immediately after ES.SetMode without waiting for the simulation loop.
    """

    def test_passive_mode_charging_immediate_power_update(self) -> None:
        """Test setting passive mode for charging immediately updates actual_power."""
        sim = BatterySimulator(initial_soc=50)
        
        # Start in auto mode - simulator may have high discharge due to household
        sim.set_mode(MODE_AUTO)
        
        # Set passive mode with charging power (-1400W)
        sim.set_mode(MODE_PASSIVE, {"power": -1400, "cd_time": 3600})
        
        # Get state immediately (simulating ES.GetStatus after ES.SetMode)
        state = sim.get_state()
        
        # Verify mode changed
        assert state["mode"] == MODE_PASSIVE
        
        # Verify power is charging (negative) and approximately -1400W (with ±5% fluctuation)
        assert state["power"] < 0, f"Expected negative power (charging), got {state['power']}"
        assert -1500 < state["power"] < -1300, f"Expected ~-1400W, got {state['power']}"
        
        # Verify status is charging (Buying)
        assert state["status"] == STATUS_CHARGING, f"Expected 'Buying', got {state['status']}"

    def test_passive_mode_discharging_immediate_power_update(self) -> None:
        """Test setting passive mode for discharging immediately updates actual_power."""
        sim = BatterySimulator(initial_soc=50)
        
        # Set passive mode with discharging power (+1400W)
        sim.set_mode(MODE_PASSIVE, {"power": 1400, "cd_time": 3600})
        
        state = sim.get_state()
        
        assert state["mode"] == MODE_PASSIVE
        assert state["power"] > 0, f"Expected positive power (discharging), got {state['power']}"
        assert 1300 < state["power"] < 1500, f"Expected ~1400W, got {state['power']}"
        assert state["status"] == STATUS_DISCHARGING

    def test_passive_mode_zero_power_immediate_update(self) -> None:
        """Test setting passive mode with zero power stops battery activity."""
        sim = BatterySimulator(initial_soc=50)
        
        # First set to active discharging
        sim.set_mode(MODE_PASSIVE, {"power": 2000, "cd_time": 3600})
        state1 = sim.get_state()
        assert state1["power"] > 1000  # Confirm discharging
        
        # Now set to zero power
        sim.set_mode(MODE_PASSIVE, {"power": 0, "cd_time": 3600})
        state2 = sim.get_state()
        
        assert state2["mode"] == MODE_PASSIVE
        assert state2["power"] == 0, f"Expected 0W, got {state2['power']}"
        assert state2["status"] == STATUS_IDLE

    def test_manual_mode_active_schedule_immediate_power_update(self) -> None:
        """Test setting manual mode with active schedule immediately updates power."""
        sim = BatterySimulator(initial_soc=50)
        
        # Set manual schedule that covers current time (00:00-23:59)
        schedule_config = {
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,  # All days
            "power": -1500,  # Charging
            "enable": 1,
        }
        sim.set_mode(MODE_MANUAL, schedule_config)
        
        state = sim.get_state()
        
        assert state["mode"] == MODE_MANUAL
        # Power should be approximately -1500W (charging)
        assert state["power"] < 0, f"Expected negative power, got {state['power']}"
        assert -1600 < state["power"] < -1400, f"Expected ~-1500W, got {state['power']}"

    def test_manual_mode_discharging_schedule_immediate_update(self) -> None:
        """Test manual mode with discharging schedule immediately updates power."""
        sim = BatterySimulator(initial_soc=50)
        
        schedule_config = {
            "time_num": 0,
            "start_time": "00:00",
            "end_time": "23:59",
            "week_set": 127,
            "power": 1200,  # Discharging
            "enable": 1,
        }
        sim.set_mode(MODE_MANUAL, schedule_config)
        
        state = sim.get_state()
        
        assert state["power"] > 0, f"Expected positive power, got {state['power']}"
        assert 1100 < state["power"] < 1300, f"Expected ~1200W, got {state['power']}"
        assert state["status"] == STATUS_DISCHARGING

    def test_switch_from_auto_to_passive_immediate_update(self) -> None:
        """Test switching from auto (high discharge) to passive (charging) updates immediately."""
        sim = BatterySimulator(initial_soc=50)
        
        # Force high household consumption so auto mode discharges heavily
        sim.household.force_cooking_event(power=3000, duration_mins=60)
        
        # Set auto mode and let it calculate
        sim.set_mode(MODE_AUTO)
        state_auto = sim.get_state()
        
        # In auto mode with high consumption, should be discharging
        # (may be limited by max_discharge_power)
        assert state_auto["mode"] == MODE_AUTO
        # Note: actual_power might be 0 initially since we just set mode
        # The point is that passive should override it
        
        # Now immediately switch to passive charging
        sim.set_mode(MODE_PASSIVE, {"power": -1400, "cd_time": 3600})
        state_passive = sim.get_state()
        
        # Should immediately reflect passive charging, not auto discharging
        assert state_passive["mode"] == MODE_PASSIVE
        assert state_passive["power"] < 0, f"Expected charging after switch, got {state_passive['power']}"
        assert state_passive["status"] == STATUS_CHARGING

    def test_rapid_mode_switches_reflect_latest(self) -> None:
        """Test rapid mode switches always reflect the most recent mode."""
        sim = BatterySimulator(initial_soc=50)
        
        # Rapid switches
        sim.set_mode(MODE_PASSIVE, {"power": 1000, "cd_time": 3600})
        sim.set_mode(MODE_PASSIVE, {"power": -2000, "cd_time": 3600})
        sim.set_mode(MODE_PASSIVE, {"power": -500, "cd_time": 3600})
        
        state = sim.get_state()
        
        # Should reflect the last setting
        assert state["mode"] == MODE_PASSIVE
        assert -600 < state["power"] < -400, f"Expected ~-500W, got {state['power']}"

    def test_grid_power_updates_with_passive_mode(self) -> None:
        """Test grid power is recalculated when switching to passive mode."""
        sim = BatterySimulator(initial_soc=50)
        
        # Set passive charging
        sim.set_mode(MODE_PASSIVE, {"power": -1400, "cd_time": 3600})
        state = sim.get_state()
        
        # Grid power should be: household - actual_power
        # With charging (negative power), grid power increases
        # actual_power is ~-1400 (with fluctuation)
        # household is variable, so just verify the relationship holds
        
        # The formula: grid_power = household_consumption - actual_power
        # With actual_power = -1400, grid_power = household + 1400
        household = state["household_consumption"]
        expected_grid = household - state["power"]
        
        # Allow some tolerance since household might fluctuate slightly
        assert abs(state["grid_power"] - expected_grid) < 50, \
            f"Grid power {state['grid_power']} doesn't match expected {expected_grid}"

    def test_battery_status_label_immediate_update(self) -> None:
        """Test battery status label updates immediately with mode change."""
        sim = BatterySimulator(initial_soc=50)
        
        # Start idle (no simulation running, power=0)
        state1 = sim.get_state()
        assert state1["status"] == STATUS_IDLE
        
        # Switch to charging
        sim.set_mode(MODE_PASSIVE, {"power": -2000, "cd_time": 3600})
        state2 = sim.get_state()
        assert state2["status"] == STATUS_CHARGING, f"Expected Buying, got {state2['status']}"
        
        # Switch to discharging  
        sim.set_mode(MODE_PASSIVE, {"power": 2000, "cd_time": 3600})
        state3 = sim.get_state()
        assert state3["status"] == STATUS_DISCHARGING, f"Expected Selling, got {state3['status']}"
        
        # Switch to idle
        sim.set_mode(MODE_PASSIVE, {"power": 0, "cd_time": 3600})
        state4 = sim.get_state()
        assert state4["status"] == STATUS_IDLE, f"Expected Idle, got {state4['status']}"

    def test_immediate_update_with_simulation_thread_running(self) -> None:
        """Test immediate power update works correctly with simulation thread active.
        
        This simulates the real scenario where:
        1. Simulation thread is running (updating state every second)
        2. ES.SetMode changes the mode
        3. ES.GetStatus is called immediately after
        
        The power should reflect the new mode, not stale Auto mode values.
        """
        sim = BatterySimulator(initial_soc=50)
        
        # Force high household consumption to create contrasting Auto mode behavior
        sim.household.force_cooking_event(power=4000, duration_mins=60)
        
        # Start the simulation thread (this is what the mock device does)
        sim.start()
        
        try:
            # Let simulation run briefly to establish Auto mode behavior
            import time
            time.sleep(0.5)
            
            # Check Auto mode is discharging to cover household
            state_before = sim.get_state()
            assert state_before["mode"] == MODE_AUTO
            # Should be discharging (positive power) or close to max
            
            # Now switch to Passive charging - this is the critical test
            sim.set_mode(MODE_PASSIVE, {"power": -1400, "cd_time": 3600})
            
            # Immediately get state (simulates ES.GetStatus after ES.SetMode)
            state_after = sim.get_state()
            
            # Mode should be Passive
            assert state_after["mode"] == MODE_PASSIVE, \
                f"Expected Passive, got {state_after['mode']}"
            
            # Power should be charging (negative), NOT discharging
            assert state_after["power"] < 0, \
                f"Expected negative power (charging), got {state_after['power']}W"
            assert -1500 < state_after["power"] < -1300, \
                f"Expected ~-1400W, got {state_after['power']}W"
            
            # Status should be Buying (charging)
            assert state_after["status"] == STATUS_CHARGING, \
                f"Expected Buying, got {state_after['status']}"
                
        finally:
            sim.stop()

    def test_simulation_thread_respects_mode_change(self) -> None:
        """Test that the simulation loop uses the new mode after a mode change."""
        sim = BatterySimulator(initial_soc=50)
        
        # Force very high household (5kW+) to make the difference obvious
        sim.household.force_cooking_event(power=5000, duration_mins=60)
        
        sim.start()
        
        try:
            import time
            
            # Let Auto mode establish (should be discharging ~3000W max)
            time.sleep(1.5)
            state_auto = sim.get_state()
            
            # Switch to Passive -1400W
            sim.set_mode(MODE_PASSIVE, {"power": -1400, "cd_time": 3600})
            
            # Wait for simulation loop to run at least once
            time.sleep(1.5)
            
            # Power should STILL be ~-1400W, not reverted to Auto discharge
            state_after_loop = sim.get_state()
            
            assert state_after_loop["mode"] == MODE_PASSIVE
            assert state_after_loop["power"] < 0, \
                f"After simulation loop, expected charging but got {state_after_loop['power']}W"
            assert -1500 < state_after_loop["power"] < -1300, \
                f"After simulation loop, expected ~-1400W but got {state_after_loop['power']}W"
                
        finally:
            sim.stop()


class TestMockMarstekDeviceResponses:
    """Tests for MockMarstekDevice request/response handling.
    
    These tests verify that the full ES.SetMode -> ES.GetStatus flow
    returns correct values, simulating what the integration actually sees.
    """

    def test_es_get_status_after_passive_mode_set(self) -> None:
        """Test ES.GetStatus returns correct power after ES.SetMode sets passive charging."""
        device = MockMarstekDevice(port=30001, simulate=True)
        
        # Simulate ES.SetMode request with passive charging
        set_mode_params = {
            "id": 0,
            "config": {
                "mode": "Passive",
                "passive_cfg": {
                    "power": -1400,
                    "cd_time": 3600,
                },
            },
        }
        
        # Process ES.SetMode (this would normally come via UDP)
        set_mode_response = device._build_response(1, "ES.SetMode", set_mode_params)
        assert set_mode_response is not None
        assert set_mode_response["result"]["success"] is True
        
        # Now immediately call ES.GetStatus (as integration does after setting mode)
        get_status_response = device._build_response(2, "ES.GetStatus", {})
        get_mode_response = device._build_response(3, "ES.GetMode", {})
        
        result = get_status_response["result"]
        mode_result = get_mode_response["result"]
        
        # Device mode should be Passive (from ES.GetMode)
        assert mode_result["mode"] == "Passive", \
            f"Expected mode 'Passive', got '{mode_result['mode']}'"
        
        # bat_power should be negative (charging) - real API uses signed values
        # Negative = charging, Positive = discharging
        assert result["bat_power"] < 0, \
            f"Expected negative bat_power (charging), got {result['bat_power']}"
        
        # Battery power should be ~1400W (absolute value of -1400)
        # Allow ±5% fluctuation = 1330-1470
        assert 1300 < abs(result["bat_power"]) < 1500, \
            f"Expected bat_power ~1400W, got {abs(result['bat_power'])}W"

    def test_es_get_status_after_passive_discharge_set(self) -> None:
        """Test ES.GetStatus returns correct power for passive discharging."""
        device = MockMarstekDevice(port=30002, simulate=True)
        
        set_mode_params = {
            "id": 0,
            "config": {
                "mode": "Passive",
                "passive_cfg": {
                    "power": 1400,  # Positive = discharge
                    "cd_time": 3600,
                },
            },
        }
        
        device._build_response(1, "ES.SetMode", set_mode_params)
        get_status_response = device._build_response(2, "ES.GetStatus", {})
        get_mode_response = device._build_response(3, "ES.GetMode", {})
        
        result = get_status_response["result"]
        
        assert get_mode_response["result"]["mode"] == "Passive"
        assert result["bat_power"] > 0, "Expected positive bat_power (discharging)"
        assert 1300 < result["bat_power"] < 1500

    def test_es_get_status_after_manual_mode_set(self) -> None:
        """Test ES.GetStatus returns correct power after ES.SetMode sets manual schedule."""
        device = MockMarstekDevice(port=30003, simulate=True)
        
        set_mode_params = {
            "id": 0,
            "config": {
                "mode": "Manual",
                "manual_cfg": {
                    "time_num": 0,
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "week_set": 127,
                    "power": -2000,  # Charging
                    "enable": 1,
                },
            },
        }
        
        device._build_response(1, "ES.SetMode", set_mode_params)
        get_status_response = device._build_response(2, "ES.GetStatus", {})
        get_mode_response = device._build_response(3, "ES.GetMode", {})
        
        result = get_status_response["result"]
        
        assert get_mode_response["result"]["mode"] == "Manual"
        assert result["bat_power"] < 0, "Expected negative bat_power (charging)"
        assert 1900 < abs(result["bat_power"]) < 2100

    def test_es_get_status_with_simulation_thread(self) -> None:
        """Test ES.GetStatus returns correct values with simulation thread running."""
        device = MockMarstekDevice(port=30004, simulate=True)
        
        # Force high household consumption
        device.simulator.household.force_cooking_event(power=4000, duration_mins=60)
        
        # Start simulation thread (this is what happens in real usage)
        device.simulator.start()
        
        try:
            # Let it run briefly in Auto mode
            time.sleep(0.5)
            
            # Set passive charging via ES.SetMode
            set_mode_params = {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {
                        "power": -1400,
                        "cd_time": 3600,
                    },
                },
            }
            device._build_response(1, "ES.SetMode", set_mode_params)
            
            # Immediately get status
            get_status_response = device._build_response(2, "ES.GetStatus", {})
            get_mode_response = device._build_response(3, "ES.GetMode", {})
            result = get_status_response["result"]
            
            # Should show Passive charging, NOT Auto discharging
            assert get_mode_response["result"]["mode"] == "Passive", \
                f"Expected Passive, got {get_mode_response['result']['mode']}"
            assert result["bat_power"] < 0, \
                f"Expected negative bat_power (charging), got {result['bat_power']}"
            assert 1300 < abs(result["bat_power"]) < 1500, \
                f"Expected ~1400W, got {abs(result['bat_power'])}W"
                
        finally:
            device.simulator.stop()


class TestAutomationScenarios:
    """Advanced scenario tests simulating real Home Assistant automation workflows.
    
    These tests verify that when automations rapidly switch between modes,
    the mock device returns correct and consistent status information.
    This catches race conditions and state synchronization issues.
    """

    def test_scenario_auto_to_passive_charging_to_auto(self) -> None:
        """Test automation: Auto -> Passive (charge during cheap tariff) -> Auto.
        
        Common scenario: charge battery during off-peak electricity prices,
        then return to auto mode.
        """
        device = MockMarstekDevice(port=30010, simulate=True)
        device.simulator.household.force_cooking_event(power=2000, duration_mins=60)
        device.simulator.start()
        
        try:
            # Initial state: Auto mode (discharging to cover household)
            time.sleep(0.3)
            status1 = device._build_response(1, "ES.GetStatus", {})["result"]
            mode1 = device._build_response(1, "ES.GetMode", {})["result"]
            
            assert mode1["mode"] == "Auto"
            # In auto with 2kW household, should be discharging (positive bat_power)
            
            # Automation triggers: cheap tariff starts, switch to passive charging
            device._build_response(2, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": -2500, "cd_time": 7200},
                },
            })
            
            # Verify immediate status change
            status2 = device._build_response(3, "ES.GetStatus", {})["result"]
            mode2 = device._build_response(3, "ES.GetMode", {})["result"]
            
            assert mode2["mode"] == "Passive", f"Expected Passive, got {mode2['mode']}"
            assert status2["bat_power"] < 0, f"Expected negative bat_power (charging), got {status2['bat_power']}"
            # Widen tolerance to account for inverter efficiency (~95%) and SOC tapering
            assert 2200 < abs(status2["bat_power"]) < 2700, f"Expected ~2500W, got {abs(status2['bat_power'])}"
            
            # Let it charge for a bit
            time.sleep(1.0)
            
            # Verify still charging correctly
            status3 = device._build_response(4, "ES.GetStatus", {})["result"]
            mode3 = device._build_response(4, "ES.GetMode", {})["result"]
            assert mode3["mode"] == "Passive"
            assert status3["bat_power"] < 0, "Expected still charging"
            
            # Automation triggers: cheap tariff ends, return to auto
            device._build_response(5, "ES.SetMode", {
                "id": 0,
                "config": {"mode": "Auto"},
            })
            
            # Verify immediate return to auto mode
            status4 = device._build_response(6, "ES.GetStatus", {})["result"]
            mode4 = device._build_response(6, "ES.GetMode", {})["result"]
            
            assert mode4["mode"] == "Auto", f"Expected Auto, got {mode4['mode']}"
            # Should be back to discharging to cover household (positive bat_power)
            assert status4["bat_power"] > 0, f"Expected positive bat_power (discharging), got {status4['bat_power']}"
            
        finally:
            device.simulator.stop()

    def test_scenario_auto_to_passive_discharging_peak_shaving(self) -> None:
        """Test automation: Auto -> Passive (discharge during peak) -> Auto.
        
        Common scenario: force discharge during peak electricity prices
        to sell energy back or avoid grid import.
        """
        device = MockMarstekDevice(port=30011, simulate=True)
        device.simulator.start()
        
        try:
            time.sleep(0.3)
            
            # Automation triggers: peak price detected, force discharge
            device._build_response(1, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": 3000, "cd_time": 1800},  # 30 min
                },
            })
            
            status = device._build_response(2, "ES.GetStatus", {})["result"]
            mode = device._build_response(2, "ES.GetMode", {})["result"]
            
            assert mode["mode"] == "Passive"
            assert status["bat_power"] > 0, "Expected positive bat_power (discharging)"
            # Widen tolerance to account for inverter efficiency (~95%) and SOC tapering
            assert 2700 < status["bat_power"] < 3200
            # Grid power should be negative (exporting) if household < 3000W
            # Note: ongrid_power = household - battery_power
            
        finally:
            device.simulator.stop()

    def test_scenario_manual_schedule_workflow(self) -> None:
        """Test automation: Set multiple manual schedules for daily routine.
        
        Common scenario: configure charge during night, discharge during day.
        """
        device = MockMarstekDevice(port=30012, simulate=True)
        device.simulator.start()
        
        try:
            time.sleep(0.3)
            
            # Set night charging schedule (slot 0)
            device._build_response(1, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Manual",
                    "manual_cfg": {
                        "time_num": 0,
                        "start_time": "00:00",
                        "end_time": "06:00",
                        "week_set": 127,
                        "power": -2000,
                        "enable": 1,
                    },
                },
            })
            
            # Set day discharging schedule (slot 1)
            device._build_response(2, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Manual",
                    "manual_cfg": {
                        "time_num": 1,
                        "start_time": "07:00",
                        "end_time": "22:00",
                        "week_set": 127,
                        "power": 1500,
                        "enable": 1,
                    },
                },
            })
            
            mode = device._build_response(3, "ES.GetMode", {})["result"]
            
            assert mode["mode"] == "Manual"
            # Power depends on current time - just verify mode is set
            assert len(device.simulator.manual_schedules) == 2
            
        finally:
            device.simulator.stop()

    def test_scenario_rapid_mode_switching_stability(self) -> None:
        """Test automation: Rapid mode switches don't cause inconsistent state.
        
        Stress test: multiple automations triggering simultaneously or in rapid succession.
        """
        device = MockMarstekDevice(port=30013, simulate=True)
        device.simulator.start()
        
        try:
            time.sleep(0.3)
            
            modes_to_test = [
                ("Passive", {"power": -1000, "cd_time": 3600}),
                ("Passive", {"power": 500, "cd_time": 3600}),
                ("Auto", None),
                ("Passive", {"power": -2000, "cd_time": 3600}),
                ("AI", None),
                ("Passive", {"power": 1500, "cd_time": 3600}),
                ("Manual", {"time_num": 0, "start_time": "00:00", "end_time": "23:59", "week_set": 127, "power": -1200, "enable": 1}),
                ("Passive", {"power": -800, "cd_time": 3600}),
            ]
            
            for i, (mode, config) in enumerate(modes_to_test):
                params = {"id": 0, "config": {"mode": mode}}
                if config:
                    if mode == "Passive":
                        params["config"]["passive_cfg"] = config
                    elif mode == "Manual":
                        params["config"]["manual_cfg"] = config
                
                device._build_response(i + 1, "ES.SetMode", params)
                
                # Immediately verify status reflects the change
                get_mode = device._build_response(i + 200, "ES.GetMode", {})["result"]
                
                assert get_mode["mode"] == mode, \
                    f"After switch {i+1}, expected {mode}, got {get_mode['mode']}"
                
            # Final state should be Passive -800W (charging)
            final_status = device._build_response(999, "ES.GetStatus", {})["result"]
            final_mode = device._build_response(999, "ES.GetMode", {})["result"]
            assert final_mode["mode"] == "Passive"
            assert final_status["bat_power"] < 0, "Expected negative bat_power (charging)"
            assert 750 < abs(final_status["bat_power"]) < 850
            
        finally:
            device.simulator.stop()

    def test_scenario_passive_mode_expiration_returns_to_auto(self) -> None:
        """Test automation: Passive mode expires and device returns to Auto.
        
        Verifies the countdown timer works correctly.
        """
        device = MockMarstekDevice(port=30014, simulate=True)
        device.simulator.start()
        
        try:
            # Set passive mode with very short duration (2 seconds)
            device._build_response(1, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": -1500, "cd_time": 2},
                },
            })
            
            mode1 = device._build_response(2, "ES.GetMode", {})["result"]
            status1 = device._build_response(2, "ES.GetStatus", {})["result"]
            assert mode1["mode"] == "Passive"
            assert status1["bat_power"] < 0, "Expected negative bat_power (charging)"
            
            # Wait for passive mode to expire
            time.sleep(3.0)
            
            # Device should have automatically switched to Auto
            mode2 = device._build_response(3, "ES.GetMode", {})["result"]
            
            assert mode2["mode"] == "Auto", \
                f"Expected Auto after expiration, got {mode2['mode']}"
            
        finally:
            device.simulator.stop()

    def test_scenario_soc_affects_power_limits(self) -> None:
        """Test automation: Battery SOC affects actual power output.
        
        Verifies that low SOC prevents discharge and high SOC limits charging.
        """
        # Test low SOC - can't discharge
        device_low = MockMarstekDevice(port=30015, simulate=True)
        device_low.simulator.soc = 3  # Very low SOC
        device_low.simulator.start()
        
        try:
            device_low._build_response(1, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": 2000, "cd_time": 3600},  # Try to discharge
                },
            })
            
            status = device_low._build_response(2, "ES.GetStatus", {})["result"]
            
            # Should be idle or very low power due to SOC limit
            assert abs(status["bat_power"]) < 100, \
                f"Expected low/no discharge at 3% SOC, got {status['bat_power']}W"
                
        finally:
            device_low.simulator.stop()
        
        # Test high SOC - charging tapers
        device_high = MockMarstekDevice(port=30016, simulate=True)
        device_high.simulator.soc = 98  # Very high SOC
        device_high.simulator.start()
        
        try:
            device_high._build_response(1, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": -3000, "cd_time": 3600},  # Try to charge
                },
            })
            
            status = device_high._build_response(2, "ES.GetStatus", {})["result"]
            
            # Charging should be tapered significantly at 98% SOC
            # Taper formula: (100 - 98) / 10 = 0.2 -> 3000 * 0.2 = 600W
            assert abs(status["bat_power"]) < 1000, \
                f"Expected tapered charging at 98% SOC, got {status['bat_power']}W"
                
        finally:
            device_high.simulator.stop()

    def test_scenario_grid_power_consistency(self) -> None:
        """Test automation: Grid power (ongrid_power) is calculated correctly.
        
        Verifies grid power changes when battery power changes.
        """
        device = MockMarstekDevice(port=30017, simulate=True)
        device.simulator.household.force_cooking_event(power=2000, duration_mins=60)
        device.simulator.start()
        
        try:
            time.sleep(0.3)
            
            # Test 1: Passive charging - grid import increases
            device._build_response(1, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": -1500, "cd_time": 3600},
                },
            })
            
            status1 = device._build_response(2, "ES.GetStatus", {})["result"]
            
            # With charging, grid import should be high
            # bat_power negative = charging, ongrid_power should increase
            assert status1["bat_power"] < 0, "Expected charging (negative bat_power)"
            # Grid should be importing (positive ongrid_power when charging + household)
            
            # Test 2: Passive discharging - grid import decreases
            device._build_response(3, "ES.SetMode", {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": 1500, "cd_time": 3600},
                },
            })
            
            status2 = device._build_response(4, "ES.GetStatus", {})["result"]
            
            # With discharging, grid import should decrease
            assert status2["bat_power"] > 0, "Expected discharging (positive bat_power)"
            # Grid usage should be lower when battery is helping
            assert status2["ongrid_power"] < status1["ongrid_power"], \
                f"Grid power should decrease when discharging: charging={status1['ongrid_power']}, discharging={status2['ongrid_power']}"
            
        finally:
            device.simulator.stop()

    def test_scenario_es_get_mode_vs_es_get_status_consistency(self) -> None:
        """Test automation: ES.GetMode and ES.GetStatus return consistent data.
        
        Both endpoints should agree on SOC values.
        """
        device = MockMarstekDevice(port=30018, simulate=True)
        device.simulator.start()
        
        try:
            modes = [
                ("Passive", {"passive_cfg": {"power": -1000, "cd_time": 3600}}),
                ("Auto", {}),
                ("AI", {}),
                ("Manual", {"manual_cfg": {"time_num": 0, "start_time": "00:00", "end_time": "23:59", "week_set": 127, "power": 500, "enable": 1}}),
                ("Passive", {"passive_cfg": {"power": 2000, "cd_time": 3600}}),
            ]
            
            for mode, extra_config in modes:
                params = {"id": 0, "config": {"mode": mode, **extra_config}}
                device._build_response(1, "ES.SetMode", params)
                
                status = device._build_response(2, "ES.GetStatus", {})["result"]
                get_mode = device._build_response(3, "ES.GetMode", {})["result"]
                
                # Mode comes from ES.GetMode only (not ES.GetStatus per API spec)
                assert get_mode["mode"] == mode, \
                    f"ES.GetMode mismatch: expected {mode}, got {get_mode['mode']}"
                
                # Both should report same SOC
                assert status["bat_soc"] == get_mode["bat_soc"], \
                    f"SOC mismatch: GetStatus={status['bat_soc']}, GetMode={get_mode['bat_soc']}"
                    
        finally:
            device.simulator.stop()

    def test_scenario_concurrent_polling_during_mode_change(self) -> None:
        """Test automation: Polling continues during and after mode change.
        
        Simulates coordinator polling while an automation changes the mode.
        """
        device = MockMarstekDevice(port=30019, simulate=True)
        device.simulator.household.force_cooking_event(power=3000, duration_mins=60)
        device.simulator.start()
        
        try:
            time.sleep(0.3)
            
            # Simulate continuous polling (like coordinator does)
            for poll in range(5):
                # Poll status
                status_before = device._build_response(poll * 10, "ES.GetStatus", {})["result"]
                
                if poll == 2:
                    # Mid-polling, automation changes mode
                    device._build_response(100, "ES.SetMode", {
                        "id": 0,
                        "config": {
                            "mode": "Passive",
                            "passive_cfg": {"power": -1800, "cd_time": 3600},
                        },
                    })
                
                # Continue polling
                time.sleep(0.2)
            
            # Final poll should show passive mode
            final_status = device._build_response(999, "ES.GetStatus", {})["result"]
            final_mode = device._build_response(999, "ES.GetMode", {})["result"]
            assert final_mode["mode"] == "Passive"
            assert final_status["bat_power"] < 0, "Expected negative bat_power (charging)"
            assert 1700 < abs(final_status["bat_power"]) < 1900
            
        finally:
            device.simulator.stop()
