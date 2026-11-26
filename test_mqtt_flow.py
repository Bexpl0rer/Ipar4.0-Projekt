import csv
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from statistics import fmean

from controller import make_command
from soil_model import (
    SoilState, advance_step, measure_moisture, STEP_MINUTES, FLOW_L_PER_MIN,
    SIMULATION_MINUTES,
)

BROKER_PORT = os.environ.get("MQTT_TEST_PORT")
# Match child-process output encoding to the UTF-8 log and pipe readers on Windows.
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def measurement(values, previous=False, minute=0):
    return {"run_id": "run", "minute": minute, "valve_open": previous,
            "moisture_percent": values}


def reference_week(mode):
    """Run the same model without network traffic for regression comparison."""
    state = SoilState()
    previous = False
    rng = Random(42)
    rows = []
    for minute in range(0, SIMULATION_MINUTES, STEP_MINUTES):
        before = state.moisture_percent
        measured = measure_moisture(state, rng)
        zones = (2,) if mode == "single" else (1, 2, 3)
        command = make_command(measurement(
            {str(z): measured[z - 1] for z in zones}, previous, minute))
        step = advance_step(state, valve_open=command["valve_open"])
        rows.append((before, measured, previous, command, step))
        previous = command["valve_open"]
        state = step.state
    return rows


class ControllerTests(unittest.TestCase):
    def test_hysteresis_boundaries_and_memory(self):
        cases = (
            (49.9, False, True), (50, False, True),
            (55, False, False), (55, True, True),
            (59.9, True, True), (60, True, False), (60.1, True, False),
        )
        for value, previous, expected in cases:
            with self.subTest(value=value, previous=previous):
                result = make_command(measurement({"2": value}, previous))
                self.assertEqual(result["decision_moisture_percent"], value)
                self.assertIs(result["valve_open"], expected)

    def test_average_and_idempotent_decision(self):
        msg = measurement({"1": 52, "2": 51, "3": 47})
        expected = {"run_id": "run", "minute": 0,
                    "decision_moisture_percent": 50.0, "valve_open": True}
        self.assertEqual(make_command(msg), expected)
        self.assertEqual(make_command(msg), expected)
        self.assertFalse(make_command(measurement({"2": 55}))["valve_open"])

    def test_invalid_measurements_and_thresholds(self):
        for values in ({"1": 48}, {"2": True}, {"2": float("nan")}):
            self.assertIsNone(make_command(measurement(values)))
        self.assertIsNone(make_command(measurement({"2": 55}, minute=1)))
        self.assertIsNone(make_command(measurement({"2": 55}, previous=1)))
        with self.assertRaises(ValueError):
            make_command(measurement({"2": 55}), 60, 50)

    def test_weekly_strategies_and_water_accounting(self):
        for mode in ("single", "average"):
            with self.subTest(mode=mode):
                rows = reference_week(mode)
                self.assertEqual(len(rows), 2016)
                opened = 0
                minutes = 0
                for before, measured, previous, command, step in rows:
                    expected = measured[1] if mode == "single" else fmean(measured)
                    self.assertAlmostEqual(command["decision_moisture_percent"], expected, places=5)
                    value = command["decision_moisture_percent"]
                    expected_open = value <= 50 or (previous and value < 60)
                    self.assertEqual(command["valve_open"], expected_open)
                    self.assertEqual(step.irrigation_minutes, 5 if expected_open else 0)
                    self.assertEqual(step.applied_water_l, step.irrigation_minutes * FLOW_L_PER_MIN)
                    self.assertTrue(all(0 <= x <= 100 for x in step.state.moisture_percent))
                    self.assertTrue(all(abs(a-b) <= 0.500001 for a, b in zip(before, measured)))
                    opened += expected_open and not previous
                    minutes += step.irrigation_minutes
                self.assertGreater(opened, 0)
                self.assertGreater(minutes, 0)
                self.assertEqual(sum(row[4].applied_water_l for row in rows),
                                 minutes * FLOW_L_PER_MIN)
        single, average = reference_week("single"), reference_week("average")
        for a, b in zip(single, average):
            for actual, measured, other_actual, other_measured in zip(a[0], a[1], b[0], b[1]):
                # Default run never clips measurements near 0 or 100.
                self.assertAlmostEqual(measured - actual, other_measured - other_actual)


@unittest.skipUnless(BROKER_PORT, "Set MQTT_TEST_PORT to enable MQTT integration tests")
class MqttFlowTests(unittest.TestCase):
    @contextmanager
    def running_controller(self, directory):
        log_path = directory / "controller.log"
        with log_path.open("w", encoding="utf-8") as log, subprocess.Popen(
            [sys.executable, "-m", "controller", "--port", BROKER_PORT,
             "--lower-threshold", "50", "--upper-threshold", "60"],
            stdout=log, stderr=subprocess.STDOUT, env=CHILD_ENV,
        ) as process:
            try:
                deadline = monotonic() + 6
                while monotonic() < deadline and process.poll() is None:
                    if "Listening on" in log_path.read_text(encoding="utf-8"):
                        break
                    sleep(0.05)
                else:
                    self.fail(f"Controller did not start: {log_path.read_text(encoding='utf-8')}")
                yield
            finally:
                if process.poll() is None:
                    process.terminate()

    def run_simulator(self, mode, output, *options):
        return subprocess.run(
            [sys.executable, "-m", "simulator", "--port", BROKER_PORT,
             "--mode", mode, "--output", str(output), *options],
            capture_output=True, text=True, encoding="utf-8", env=CHILD_ENV, timeout=300,
        )

    def test_reference_week_over_mqtt(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            with self.running_controller(directory):
                for mode in ("single", "average"):
                    with self.subTest(mode=mode):
                        output = directory / f"{mode}.csv"
                        result = self.run_simulator(mode, output)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        with output.open(newline="", encoding="utf-8") as log:
                            rows = list(csv.DictReader(log))
                        expected = reference_week(mode)
                        self.assertEqual([int(row["minute"]) for row in rows],
                                         list(range(0, SIMULATION_MINUTES, STEP_MINUTES)))
                        self.assertEqual(len({row["run_id"] for row in rows}), 1)
                        for row, (before, measured, previous, command, step) in zip(rows, expected):
                            self.assertEqual(int(row["previous_valve_open"]), int(previous))
                            self.assertEqual(int(row["valve_open"]), int(command["valve_open"]))
                            self.assertEqual(float(row["decision_moisture_percent"]),
                                             command["decision_moisture_percent"])
                            self.assertEqual(int(row["irrigation_minutes"]), step.irrigation_minutes)
                            self.assertEqual(float(row["applied_water_l"]), step.applied_water_l)
                            for zone in (1, 2, 3):
                                self.assertEqual(float(row[f"zone_{zone}_before_percent"]), before[zone-1])
                                self.assertEqual(float(row[f"zone_{zone}_measured_percent"]), measured[zone-1])
                                self.assertEqual(float(row[f"zone_{zone}_after_percent"]),
                                                 step.state.moisture_percent[zone-1])
                        minutes = sum(step.irrigation_minutes for _, _, _, _, step in expected)
                        self.assertIn(f"applied {minutes * FLOW_L_PER_MIN:g} L", result.stdout)
                        dry = [sum(STEP_MINUTES for row in expected if row[0][z] < 40) / 60
                               for z in range(3)]
                        for z, hours in enumerate(dry, 1):
                            self.assertIn(f"zone {z}: {hours:.3f}", result.stdout)

    def test_missing_controller_does_not_advance_soil(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "no-controller.csv"
            result = self.run_simulator("single", output, "--hours", "1", "--timeout", "1")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No matching valve command", result.stderr)
            with output.open(newline="", encoding="utf-8") as log:
                self.assertEqual(list(csv.DictReader(log)), [])
