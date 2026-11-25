import csv
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from controller import make_command


BROKER_PORT = os.environ.get("MQTT_TEST_PORT")


class ControllerTests(unittest.TestCase):
    def test_single_and_average_decisions(self):
        cases = (
            ({"2": 49.9}, 49.9, True),
            ({"2": 50}, 50, False),
            ({"2": 50.1}, 50.1, False),
            ({"1": 52, "2": 51, "3": 44}, 49, True),
            ({"1": 52, "2": 51, "3": 47}, 50, False),
        )
        for moisture, value, valve_open in cases:
            with self.subTest(moisture=moisture):
                command = make_command({
                    "run_id": "run", "hour": 4, "moisture_percent": moisture,
                }, threshold=50)
                self.assertEqual(command, {
                    "run_id": "run", "hour": 4,
                    "decision_moisture_percent": value, "valve_open": valve_open,
                })

    def test_invalid_measurements_are_ignored(self):
        for moisture in ({"1": 48}, {"2": True}, {"2": float("nan")}):
            with self.subTest(moisture=moisture):
                self.assertIsNone(make_command({
                    "run_id": "run", "hour": 4, "moisture_percent": moisture,
                }, threshold=50))


@unittest.skipUnless(BROKER_PORT, "Set MQTT_TEST_PORT to enable MQTT integration tests")
class MqttFlowTests(unittest.TestCase):
    @contextmanager
    def running_controller(self, directory, threshold):
        log_path = directory / "controller.log"
        with log_path.open("w", encoding="utf-8") as log, subprocess.Popen(
            [sys.executable, "-m", "controller", "--port", BROKER_PORT,
             "--threshold", str(threshold)], stdout=log, stderr=subprocess.STDOUT,
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
            capture_output=True, text=True, timeout=60,
        )

    def test_reference_week_over_mqtt(self):
        cases = {
            50: (("single", 60, 52), ("average", 66, 16)),
            55: (("single", 66, 15), ("average", 66, 0)),
        }
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            for threshold, strategies in cases.items():
                with self.running_controller(directory, threshold):
                    for mode, litres, dry_hours in strategies:
                        with self.subTest(threshold=threshold, mode=mode):
                            output = directory / f"{mode}-{threshold}.csv"
                            result = self.run_simulator(mode, output)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            with output.open(newline="", encoding="utf-8") as log:
                                rows = list(csv.DictReader(log))
                            self.assertEqual([int(row["hour"]) for row in rows], list(range(168)))
                            self.assertEqual(len({row["run_id"] for row in rows}), 1)
                            self.assertEqual(sum(float(row["applied_water_l"]) for row in rows), litres)
                            self.assertEqual(tuple(
                                sum(not 40 <= float(row[f"zone_{zone}_before_percent"]) <= 75
                                    for row in rows)
                                for zone in (1, 2, 3)
                            ), (0, 0, dry_hours))
                            for row, following in zip(rows, rows[1:]):
                                for zone in (1, 2, 3):
                                    self.assertEqual(row[f"zone_{zone}_after_percent"],
                                                     following[f"zone_{zone}_before_percent"])

    def test_missing_controller_does_not_advance_soil(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "no-controller.csv"
            result = self.run_simulator("single", output, "--hours", "1", "--timeout", "1")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No matching valve command", result.stderr)
            with output.open(newline="", encoding="utf-8") as log:
                self.assertEqual(list(csv.DictReader(log)), [])
