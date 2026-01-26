#!/usr/bin/env python3
"""Mock Marstek device for testing UDP discovery and communication.

Response structures captured from real VenusE 3.0 device at 192.168.0.152.
Enhanced with realistic battery simulation including:
- Dynamic SOC changes based on power flow
- Power fluctuations
- Mode transitions (Auto, Manual, Passive, AI)
- Passive mode countdown timer
- Manual schedule simulation
- Realistic household power consumption patterns for Auto mode
"""

import argparse
import json
import math
import random
import socket
import threading
import time
from datetime import datetime
from typing import Any

# Default mock device configuration (captured from real device)
DEFAULT_CONFIG = {
    "device": "VenusE 3.0",
    "ver": 145,
    "ble_mac": "009b08a5aa39",
    "wifi_mac": "7483c2315cf8",
    "wifi_name": "AirPort-38",
}

# Battery capacity in Wh (typical for Venus 3.0 is ~5120Wh)
BATTERY_CAPACITY_WH = 5120

# Mode constants
MODE_AUTO = "Auto"
MODE_AI = "AI"
MODE_MANUAL = "Manual"
MODE_PASSIVE = "Passive"

# Battery status labels
STATUS_CHARGING = "Buying"
STATUS_DISCHARGING = "Selling"
STATUS_IDLE = "Idle"


def get_local_ip() -> str:
    """Get the local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class HouseholdSimulator:
    """Simulates realistic household power consumption (what a P1 meter would see)."""

    def __init__(self):
        # Base load: fridge, standby devices, networking etc (100-300W)
        self.base_load = 200

        # Current consumption state
        self.current_consumption = self.base_load
        self._lock = threading.Lock()

        # Event simulation
        self._cooking_until: float = 0
        self._cooking_power: int = 0
        self._appliance_until: float = 0
        self._appliance_power: int = 0

        # Time-based patterns
        self._last_event_check: float = 0
        
        # Second-by-second fluctuation state
        self._fluctuation_base: int = 0
        self._fluctuation_target: int = 0
        self._fluctuation_step: float = 0
        self._last_fluctuation_update: float = 0

    def get_consumption(self) -> int:
        """Get current household power consumption in watts (positive = consuming from grid)."""
        with self._lock:
            now = time.time()

            # Check for random events every 30 seconds
            if now - self._last_event_check > 30:
                self._last_event_check = now
                self._maybe_trigger_event(now)

            # Calculate current consumption
            consumption = self.base_load

            # Add time-of-day variation (morning/evening peaks)
            hour = datetime.now().hour
            consumption += self._get_time_based_load(hour)

            # Add active events
            if now < self._cooking_until:
                consumption += self._cooking_power
            if now < self._appliance_until:
                consumption += self._appliance_power

            # Add realistic second-by-second micro-fluctuations
            # This simulates things like: fridge compressor cycling, HVAC,
            # lights dimming, devices switching states, etc.
            consumption += self._get_micro_fluctuation(now)

            self.current_consumption = max(50, consumption)  # Minimum 50W
            return self.current_consumption

    def _get_micro_fluctuation(self, now: float) -> int:
        """Get micro-fluctuations that change every second."""
        # Update fluctuation target every 1-3 seconds
        if now - self._last_fluctuation_update > random.uniform(0.5, 2.0):
            self._last_fluctuation_update = now
            self._fluctuation_base = self._fluctuation_target
            
            # Random walk with occasional spikes
            if random.random() < 0.1:  # 10% chance of a spike
                # Spike: sudden change of 50-200W (device turning on/off)
                spike = random.choice([-1, 1]) * random.randint(50, 200)
                self._fluctuation_target = max(-100, min(300, self._fluctuation_base + spike))
            else:
                # Normal drift: ±20W
                drift = random.randint(-20, 20)
                self._fluctuation_target = max(-50, min(150, self._fluctuation_base + drift))
        
        # Smooth interpolation between base and target
        elapsed = now - self._last_fluctuation_update
        progress = min(1.0, elapsed / 1.0)  # 1 second transition
        current = self._fluctuation_base + (self._fluctuation_target - self._fluctuation_base) * progress
        
        return int(current)

    def _get_time_based_load(self, hour: int) -> int:
        """Get additional load based on time of day."""
        # Morning peak (6-9): getting ready, breakfast
        if 6 <= hour < 9:
            return random.randint(200, 500)
        # Midday (9-17): lower usage if no one home
        elif 9 <= hour < 17:
            return random.randint(50, 150)
        # Evening peak (17-22): cooking, TV, lights
        elif 17 <= hour < 22:
            return random.randint(300, 800)
        # Night (22-6): minimal
        else:
            return random.randint(0, 50)

    def _maybe_trigger_event(self, now: float) -> None:
        """Randomly trigger household events."""
        hour = datetime.now().hour

        # Cooking events (more likely during meal times)
        if now >= self._cooking_until:
            cooking_chance = 0.05  # 5% base chance every 30s
            if hour in [7, 8, 12, 13, 18, 19, 20]:  # Meal times
                cooking_chance = 0.20  # 20% during meal times

            if random.random() < cooking_chance:
                # Cooking event: 1500-3000W for 5-30 minutes
                self._cooking_power = random.randint(1500, 3000)
                self._cooking_until = now + random.randint(5, 30) * 60
                print(f"[HOUSE] 🍳 Cooking started: {self._cooking_power}W for {int((self._cooking_until - now) / 60)} min")

        # Appliance events (washing machine, dryer, dishwasher, etc.)
        if now >= self._appliance_until:
            appliance_chance = 0.03  # 3% base chance every 30s

            if random.random() < appliance_chance:
                appliances = [
                    ("Washing machine", 400, 800, 30, 60),
                    ("Dryer", 2000, 3000, 45, 90),
                    ("Dishwasher", 1200, 1800, 60, 120),
                    ("Vacuum cleaner", 800, 1500, 10, 30),
                    ("Iron", 1000, 2000, 10, 20),
                    ("Kettle", 2000, 3000, 2, 5),
                    ("Microwave", 800, 1200, 2, 10),
                ]
                name, min_power, max_power, min_mins, max_mins = random.choice(appliances)
                self._appliance_power = random.randint(min_power, max_power)
                self._appliance_until = now + random.randint(min_mins, max_mins) * 60
                print(f"[HOUSE] 🔌 {name} started: {self._appliance_power}W for {int((self._appliance_until - now) / 60)} min")

    def force_cooking_event(self, power: int = 2500, duration_mins: int = 15) -> None:
        """Force a cooking event for testing."""
        with self._lock:
            self._cooking_power = power
            self._cooking_until = time.time() + duration_mins * 60
            print(f"[HOUSE] 🍳 Forced cooking: {power}W for {duration_mins} min")


class WiFiSimulator:
    """Simulates realistic WiFi signal strength variations."""

    def __init__(self, base_rssi: int = -55):
        """Initialize WiFi simulator.
        
        Args:
            base_rssi: Base RSSI value in dBm (typical: -30 excellent to -90 poor)
        """
        self.base_rssi = base_rssi
        self._current_rssi = base_rssi
        self._last_update = 0.0
        self._drift_target = base_rssi
        self._interference_until = 0.0
        self._interference_amount = 0

    def get_rssi(self) -> int:
        """Get current RSSI with realistic variations.
        
        Returns realistic WiFi signal variations:
        - Base signal strength (-30 to -90 dBm typical)
        - Slow drift (±5 dBm over minutes)
        - Fast micro-fluctuations (±2 dBm per second)
        - Occasional interference events (±10-20 dBm)
        """
        now = time.time()
        
        # Update drift target every 30-60 seconds
        if now - self._last_update > random.uniform(30, 60):
            self._last_update = now
            # Drift within ±10 dBm of base, clamped to realistic range
            drift = random.randint(-5, 5)
            self._drift_target = max(-90, min(-30, self.base_rssi + drift))
            
            # 5% chance of interference event
            if random.random() < 0.05:
                self._interference_amount = random.randint(10, 20)
                self._interference_until = now + random.uniform(5, 30)
        
        # Gradual move toward drift target
        if self._current_rssi < self._drift_target:
            self._current_rssi = min(self._current_rssi + 1, self._drift_target)
        elif self._current_rssi > self._drift_target:
            self._current_rssi = max(self._current_rssi - 1, self._drift_target)
        
        # Add micro-fluctuation
        rssi = self._current_rssi + random.randint(-2, 2)
        
        # Apply interference if active
        if now < self._interference_until:
            rssi -= self._interference_amount
        
        # Clamp to realistic range
        return max(-95, min(-25, rssi))


class BatterySimulator:
    """Simulates realistic battery behavior over time."""

    def __init__(
        self,
        initial_soc: int = 50,
        capacity_wh: int = BATTERY_CAPACITY_WH,
        max_charge_power: int = 3000,
        max_discharge_power: int = 3000,
    ):
        self.soc = initial_soc  # State of charge (0-100%)
        self.capacity_wh = capacity_wh
        self.max_charge_power = max_charge_power
        self.max_discharge_power = max_discharge_power

        # Current state
        self.mode = MODE_AUTO
        self.target_power = 0  # Target power for passive/manual modes
        self.actual_power = 0  # Actual power with fluctuations
        self.grid_power = 0  # Power from/to grid (what P1 meter sees)
        self.passive_end_time: float | None = None  # When passive mode ends
        self.manual_schedules: list[dict[str, Any]] = []  # Manual mode schedules

        # Battery temperature simulation (20-45°C typical range)
        self.base_temp = 25.0  # Ambient temp
        self.battery_temp = self.base_temp
        
        # CT (Current Transformer) state - assume connected by default
        self.ct_connected = True

        # Household simulator for auto mode
        self.household = HouseholdSimulator()
        
        # WiFi simulator
        self.wifi = WiFiSimulator(base_rssi=-55)

        # Simulation settings
        self.power_fluctuation_pct = 5  # ±5% power fluctuation
        self.update_interval = 1.0  # Update every second
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the battery simulation thread."""
        self._running = True
        self._thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the battery simulation thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _simulation_loop(self) -> None:
        """Main simulation loop - updates battery state."""
        last_update = time.time()
        while self._running:
            time.sleep(0.1)  # Check more frequently for responsiveness

            now = time.time()
            elapsed = now - last_update
            if elapsed < self.update_interval:
                continue
            last_update = now

            with self._lock:
                self._update_state(elapsed)

    def _update_state(self, elapsed_seconds: float) -> None:
        """Update battery state based on elapsed time."""
        # Check if passive mode has expired
        if self.mode == MODE_PASSIVE and self.passive_end_time:
            if time.time() >= self.passive_end_time:
                print(f"[SIM] Passive mode expired, switching to Auto")
                self.mode = MODE_AUTO
                self.target_power = 0
                self.passive_end_time = None

        # Get household consumption
        household_consumption = self.household.get_consumption()

        # Determine battery target power based on mode
        target = self._calculate_target_power(household_consumption)

        # Apply power limits based on SOC
        target = self._apply_soc_limits(target)

        # Add realistic fluctuation
        if target != 0:
            fluctuation = target * (random.uniform(-1, 1) * self.power_fluctuation_pct / 100)
            self.actual_power = int(target + fluctuation)
        else:
            self.actual_power = 0

        # Calculate grid power (what the P1 meter would see)
        # Positive grid_power = importing from grid (buying)
        # Negative grid_power = exporting to grid (selling)
        # Battery discharge (positive actual_power) reduces grid import
        # Battery charge (negative actual_power) increases grid import
        self.grid_power = household_consumption - self.actual_power

        # Update SOC based on power flow
        # energy_wh = power_w * hours
        hours = elapsed_seconds / 3600
        energy_wh = self.actual_power * hours

        # Negative power = charging = SOC increases
        # Positive power = discharging = SOC decreases
        soc_change = -(energy_wh / self.capacity_wh) * 100
        new_soc = self.soc + soc_change
        self.soc = max(0, min(100, new_soc))
        
        # Update battery temperature based on power flow
        # Battery heats up during charge/discharge, cools toward ambient when idle
        power_abs = abs(self.actual_power)
        if power_abs > 100:
            # Heat up: more power = more heat (up to +0.5°C per update at max power)
            heat_factor = min(power_abs / self.max_discharge_power, 1.0)
            self.battery_temp += heat_factor * 0.3 * random.uniform(0.8, 1.2)
        else:
            # Cool down toward ambient (±0.1°C per update)
            if self.battery_temp > self.base_temp:
                self.battery_temp -= 0.1 * random.uniform(0.5, 1.5)
            elif self.battery_temp < self.base_temp:
                self.battery_temp += 0.1 * random.uniform(0.5, 1.5)
        
        # Clamp temperature to realistic range
        self.battery_temp = max(15.0, min(50.0, self.battery_temp))

    def _calculate_target_power(self, household_consumption: int) -> int:
        """Calculate target power based on current mode and household consumption."""
        if self.mode == MODE_PASSIVE:
            # Passive mode: fixed power for set duration
            return self.target_power

        if self.mode == MODE_MANUAL:
            # Manual mode: check active schedules
            schedule = self._get_active_schedule()
            if schedule:
                return schedule.get("power", 0)
            return 0

        if self.mode == MODE_AUTO:
            # Auto mode: try to keep grid power at 0 (zero export/import)
            # This simulates reading from a P1 meter and compensating
            # Discharge to cover household consumption, charge from excess solar (none in this sim)

            # Target: make grid_power = 0
            # grid_power = household_consumption + battery_power
            # 0 = household_consumption + battery_power
            # battery_power = -household_consumption (should discharge to cover)

            # But we want to discharge (positive power) to cover consumption
            target = household_consumption  # Discharge to cover household

            # Limit to available capacity
            target = min(target, self.max_discharge_power)

            # Don't discharge if SOC is too low (reserve 10%)
            if self.soc < 10:
                target = 0

            return target

        if self.mode == MODE_AI:
            # AI mode: similar to auto but with predictive behavior
            # Simulates smarter decisions based on patterns
            target = household_consumption

            # AI might not discharge fully during low-usage periods to save for peaks
            hour = datetime.now().hour
            if 9 <= hour < 17:  # Daytime: save some for evening peak
                target = int(target * 0.7)

            # Reserve more battery during evening for expected peaks
            if 17 <= hour < 22 and self.soc < 30:
                target = int(target * 0.5)

            target = min(target, self.max_discharge_power)
            if self.soc < 15:
                target = 0

            return target

        return 0

    def _apply_soc_limits(self, target: int) -> int:
        """Apply power limits based on SOC."""
        # Can't discharge below 5% SOC
        if target > 0 and self.soc <= 5:
            return 0
        # Can't charge above 100% SOC
        if target < 0 and self.soc >= 100:
            return 0
        # Taper charging as we approach 100%
        if target < 0 and self.soc > 90:
            taper = (100 - self.soc) / 10  # 0-1 scale
            target = int(target * taper)
        # Taper discharging as we approach 0%
        if target > 0 and self.soc < 10:
            taper = self.soc / 10  # 0-1 scale
            target = int(target * taper)
        return target

    def _apply_immediate_power_update(self) -> None:
        """Immediately update actual_power and grid_power to reflect current mode.

        Called after mode changes to ensure ES.GetStatus returns correct values
        without waiting for the next simulation loop iteration.
        Must be called while holding self._lock.
        """
        household_consumption = self.household.get_consumption()
        target = self._calculate_target_power(household_consumption)
        target = self._apply_soc_limits(target)

        # Apply fluctuation
        if target != 0:
            fluctuation = target * (random.uniform(-1, 1) * self.power_fluctuation_pct / 100)
            self.actual_power = int(target + fluctuation)
        else:
            self.actual_power = 0

        # Update grid power
        self.grid_power = household_consumption - self.actual_power
        print(f"[SIM] Immediate power update: actual={self.actual_power}W, grid={self.grid_power}W")

    def _get_active_schedule(self) -> dict[str, Any] | None:
        """Get the currently active manual schedule, if any."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()  # 0=Monday

        for schedule in self.manual_schedules:
            if not schedule.get("enable", True):
                continue

            week_set = schedule.get("week_set", 127)
            # Check if current day is in week_set (bit 0=Mon, bit 6=Sun)
            if not (week_set & (1 << current_day)):
                continue

            start = schedule.get("start_time", "00:00")
            end = schedule.get("end_time", "23:59")

            if start <= current_time <= end:
                return schedule

        return None

    def set_mode(self, mode: str, config: dict[str, Any] | None = None) -> None:
        """Set operating mode with optional configuration."""
        with self._lock:
            self.mode = mode
            print(f"[SIM] Mode set to: {mode}")

            if mode == MODE_PASSIVE and config:
                self.target_power = config.get("power", 0)
                duration = config.get("cd_time", 3600)
                self.passive_end_time = time.time() + duration
                print(f"[SIM] Passive: power={self.target_power}W, duration={duration}s")
                # Immediately update actual_power to reflect new mode
                # This prevents stale values being returned by ES.GetStatus
                self._apply_immediate_power_update()

            elif mode == MODE_MANUAL and config:
                # Update manual schedule slot
                slot = config.get("time_num", 0)
                schedule = {
                    "time_num": slot,
                    "start_time": config.get("start_time", "00:00"),
                    "end_time": config.get("end_time", "23:59"),
                    "week_set": config.get("week_set", 127),
                    "power": config.get("power", 0),
                    "enable": config.get("enable", 1) == 1,
                }
                # Update or add schedule
                for i, s in enumerate(self.manual_schedules):
                    if s.get("time_num") == slot:
                        self.manual_schedules[i] = schedule
                        break
                else:
                    self.manual_schedules.append(schedule)
                print(f"[SIM] Manual schedule slot {slot}: {schedule}")
                # Immediately update actual_power to reflect new schedule
                self._apply_immediate_power_update()

            else:
                # For Auto/AI mode changes, also update immediately
                self._apply_immediate_power_update()

    def get_state(self) -> dict[str, Any]:
        """Get current battery state."""
        with self._lock:
            # Determine battery status label
            if self.actual_power < -50:
                status = STATUS_CHARGING
            elif self.actual_power > 50:
                status = STATUS_DISCHARGING
            else:
                status = STATUS_IDLE

            # Calculate passive remaining time
            passive_remaining = 0
            if self.passive_end_time and self.mode == MODE_PASSIVE:
                passive_remaining = max(0, int(self.passive_end_time - time.time()))

            # Build passive_cfg for number entities
            passive_cfg = None
            if self.mode == MODE_PASSIVE:
                passive_cfg = {
                    "power": self.target_power,
                    "cd_time": passive_remaining,
                }

            # Determine charge/discharge flags based on SOC and state
            charg_flag = 1 if self.soc < 100 else 0
            dischrg_flag = 1 if self.soc > 5 else 0

            return {
                "soc": int(self.soc),
                "power": self.actual_power,
                "mode": self.mode,
                "status": status,
                "grid_power": self.grid_power,
                "household_consumption": self.household.current_consumption,
                "passive_remaining": passive_remaining,
                "passive_cfg": passive_cfg,
                # New fields for extended API support
                "wifi_rssi": self.wifi.get_rssi(),
                "battery_temp": round(self.battery_temp, 1),
                "ct_connected": self.ct_connected,
                "charg_flag": charg_flag,
                "dischrg_flag": dischrg_flag,
            }


class MockMarstekDevice:
    """Mock Marstek device that responds to UDP requests."""

    def __init__(
        self,
        port: int = 30000,
        device_config: dict[str, Any] | None = None,
        ip_override: str | None = None,
        initial_soc: int = 50,
        simulate: bool = True,
    ):
        self.port = port
        self.config = {**DEFAULT_CONFIG, **(device_config or {})}
        self.ip = ip_override or get_local_ip()
        self.sock: socket.socket | None = None

        # Battery simulator
        self.simulator = BatterySimulator(initial_soc=initial_soc)
        self.simulate = simulate

        # Static fallback values (used if simulation disabled)
        self._static_soc = initial_soc
        self._static_power = 0
        self._static_mode = MODE_AUTO

    def start(self) -> None:
        """Start the mock device server."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.bind(("0.0.0.0", self.port))

        print(f"=" * 60)
        print(f"MOCK MARSTEK DEVICE")
        print(f"=" * 60)
        print(f"Device: {self.config['device']}")
        print(f"BLE MAC: {self.config['ble_mac']}")
        print(f"WiFi MAC: {self.config['wifi_mac']}")
        print(f"IP: {self.ip}")
        print(f"Listening on UDP port {self.port}")
        print(f"Simulation: {'ENABLED' if self.simulate else 'DISABLED'}")
        print(f"Initial SOC: {self.simulator.soc}%")
        print(f"=" * 60)
        print(f"Mode behaviors:")
        print(f"  Auto: Discharges to offset household consumption (P1 meter = 0)")
        print(f"  Manual: Follows scheduled charge/discharge times")
        print(f"  Passive: Fixed power for set duration")
        print(f"=" * 60)
        print()

        if self.simulate:
            self.simulator.start()
            # Start status display thread
            self._status_thread = threading.Thread(target=self._status_display, daemon=True)
            self._status_thread.start()

        try:
            while True:
                self._handle_request()
        except KeyboardInterrupt:
            print("\nShutting down mock device...")
        finally:
            if self.simulate:
                self.simulator.stop()
            if self.sock:
                self.sock.close()

    def _status_display(self) -> None:
        """Display battery status periodically."""
        while True:
            time.sleep(5)
            state = self.simulator.get_state()
            power_indicator = (
                f"⚡ Charging" if state["power"] < 0
                else f"🔋 Discharging" if state["power"] > 0
                else "💤 Idle"
            )
            grid_indicator = (
                f"📥 Buying {state['grid_power']}W" if state["grid_power"] > 50
                else f"📤 Selling {-state['grid_power']}W" if state["grid_power"] < -50
                else "⚖️ Balanced"
            )
            passive_info = ""
            if state["mode"] == MODE_PASSIVE and state["passive_remaining"] > 0:
                passive_info = f" | ⏱️ {state['passive_remaining']}s left"

            print(
                f"[STATUS] SOC: {state['soc']}% | Batt: {state['power']}W | "
                f"🏠 {state['household_consumption']}W | {grid_indicator} | "
                f"Mode: {state['mode']}{passive_info} | {power_indicator}"
            )

    def _handle_request(self) -> None:
        """Handle incoming UDP request."""
        data, addr = self.sock.recvfrom(4096)
        sender_ip, sender_port = addr

        try:
            request = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            print(f"[{time.strftime('%H:%M:%S')}] Invalid JSON from {sender_ip}:{sender_port}")
            return

        request_id = request.get("id", 0)
        method = request.get("method", "")

        print(f"[{time.strftime('%H:%M:%S')}] Request from {sender_ip}:{sender_port}")
        print(f"   Method: {method}")
        print(f"   ID: {request_id}")

        response = self._build_response(request_id, method, request.get("params", {}))

        if response:
            response_bytes = json.dumps(response).encode("utf-8")
            self.sock.sendto(response_bytes, addr)
            print(f"   -> Sent response: {method}")
        else:
            print(f"   -> Unknown method, no response")

        print()

    def _get_state(self) -> dict[str, Any]:
        """Get current device state from simulator or static values."""
        if self.simulate:
            return self.simulator.get_state()
        return {
            "soc": self._static_soc,
            "power": self._static_power,
            "mode": self._static_mode,
            "status": STATUS_IDLE,
            "grid_power": 0,
            "household_consumption": 0,
            "passive_remaining": 0,
            "passive_cfg": None,
            "wifi_rssi": -55,
            "battery_temp": 25.0,
            "ct_connected": True,
            "charg_flag": 1,
            "dischrg_flag": 1,
        }

    def _build_response(
        self, request_id: int, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Build response for a given method."""
        src = f"{self.config['device']}-{self.config['ble_mac']}"
        state = self._get_state()

        if method == "Marstek.GetDevice":
            return {
                "id": request_id,
                "src": src,
                "result": {
                    "device": self.config["device"],
                    "ver": self.config["ver"],
                    "ble_mac": self.config["ble_mac"],
                    "wifi_mac": self.config["wifi_mac"],
                    "wifi_name": self.config["wifi_name"],
                    "ip": self.ip,
                },
            }

        elif method == "ES.GetStatus":
            # Match the real API spec from docs/marstek_device_openapi.MD
            return {
                "id": request_id,
                "src": src,
                "result": {
                    "id": 0,
                    "bat_soc": state["soc"],
                    "bat_cap": 5120,  # Simulated battery capacity in Wh
                    "pv_power": 0,
                    "ongrid_power": state["grid_power"],
                    "offgrid_power": 0,
                    "bat_power": state["power"],  # Positive = discharging, Negative = charging
                    "total_pv_energy": 0,
                    "total_grid_output_energy": 1000,
                    "total_grid_input_energy": 500,
                    "total_load_energy": 800,
                },
            }

        elif method == "ES.GetMode":
            # Official API spec: ES.GetMode returns only these fields
            # NOTE: Device does NOT return passive_cfg in ES.GetMode!
            # The integration stores passive_cfg locally when set via ES.SetMode
            result = {
                "id": 0,
                "mode": state["mode"],
                "ongrid_power": state["grid_power"],
                "offgrid_power": 0,
                "bat_soc": state["soc"],
            }
            return {
                "id": request_id,
                "src": src,
                "result": result,
            }

        elif method == "PV.GetStatus":
            return {
                "id": request_id,
                "src": src,
                "result": {
                    "pv1_power": 0,
                    "pv1_voltage": 0,
                    "pv1_current": 0,
                    "pv1_state": 0,
                    "pv2_power": 0,
                    "pv2_voltage": 0,
                    "pv2_current": 0,
                    "pv2_state": 0,
                    "pv3_power": 0,
                    "pv3_voltage": 0,
                    "pv3_current": 0,
                    "pv3_state": 0,
                    "pv4_power": 0,
                    "pv4_voltage": 0,
                    "pv4_current": 0,
                    "pv4_state": 0,
                },
            }

        elif method == "Wifi.GetStatus":
            # Realistic WiFi status with variable signal strength
            return {
                "id": request_id,
                "src": src,
                "result": {
                    "rssi": state["wifi_rssi"],
                    "ssid": self.config.get("wifi_name", "AirPort-38"),
                    "sta_ip": self.ip,
                    "sta_gate": ".".join(self.ip.split(".")[:3]) + ".1",
                    "sta_mask": "255.255.255.0",
                    "sta_dns": ".".join(self.ip.split(".")[:3]) + ".1",
                },
            }

        elif method == "EM.GetStatus":
            # Energy Meter / CT clamp status
            # Simulate 3-phase power readings
            grid_power = state["grid_power"]
            # Distribute power roughly equally across phases with some variation
            phase_variation = random.uniform(0.8, 1.2)
            a_power = int(grid_power * 0.33 * phase_variation)
            b_power = int(grid_power * 0.33 * random.uniform(0.8, 1.2))
            c_power = grid_power - a_power - b_power  # Ensure total adds up
            
            return {
                "id": request_id,
                "src": src,
                "result": {
                    "ct_state": 1 if state["ct_connected"] else 0,
                    "a_power": a_power,
                    "b_power": b_power,
                    "c_power": c_power,
                    "total_power": grid_power,
                },
            }

        elif method == "Bat.GetStatus":
            # Detailed battery status
            return {
                "id": request_id,
                "src": src,
                "result": {
                    "bat_temp": state["battery_temp"],
                    "charg_flag": state["charg_flag"],
                    "dischrg_flag": state["dischrg_flag"],
                    "bat_capacity": int(self.simulator.capacity_wh * state["soc"] / 100),
                    "rated_capacity": self.simulator.capacity_wh,
                    "soc": state["soc"],
                },
            }

        elif method == "ES.SetMode":
            # Handle mode changes
            config = params.get("config", {})
            mode = config.get("mode", MODE_AUTO)

            if self.simulate:
                if mode == MODE_PASSIVE:
                    passive_cfg = config.get("passive_cfg", {})
                    self.simulator.set_mode(mode, passive_cfg)
                elif mode == MODE_MANUAL:
                    manual_cfg = config.get("manual_cfg", {})
                    self.simulator.set_mode(mode, manual_cfg)
                else:
                    self.simulator.set_mode(mode)
            else:
                self._static_mode = mode

            print(f"   Mode changed to: {mode}")

            return {
                "id": request_id,
                "src": src,
                "result": {"success": True},
            }

        return None


def main():
    parser = argparse.ArgumentParser(
        description="Mock Marstek device for testing with realistic battery simulation"
    )
    parser.add_argument("--port", type=int, default=30000, help="UDP port (default: 30000)")
    parser.add_argument("--ip", type=str, help="Override reported IP address")
    parser.add_argument("--device", type=str, default="VenusE 3.0", help="Device type")
    parser.add_argument("--ble-mac", type=str, default="009b08a5aa39", help="BLE MAC address")
    parser.add_argument("--wifi-mac", type=str, default="7483c2315cf8", help="WiFi MAC address")
    parser.add_argument("--soc", type=int, default=50, help="Initial battery SOC percentage (default: 50)")
    parser.add_argument(
        "--no-simulate",
        action="store_true",
        help="Disable dynamic simulation (static values only)",
    )
    args = parser.parse_args()

    config = {
        "device": args.device,
        "ble_mac": args.ble_mac.replace(":", "").lower(),
        "wifi_mac": args.wifi_mac.replace(":", "").lower(),
    }

    device = MockMarstekDevice(
        port=args.port,
        device_config=config,
        ip_override=args.ip,
        initial_soc=args.soc,
        simulate=not args.no_simulate,
    )
    device.start()


if __name__ == "__main__":
    main()
