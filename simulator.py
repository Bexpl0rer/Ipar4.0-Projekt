"""Run the five-minute soil model through MQTT and log each decision."""

import argparse
import csv
import math
from pathlib import Path
from queue import Empty
from random import Random
from time import monotonic
from uuid import uuid4

from mqtt_link import COMMAND_TOPIC, MEASUREMENT_TOPIC, MqttLink, is_percent
from soil_model import (
    SIMULATION_HOURS, STEP_MINUTES, FLOW_L_PER_MIN, DEFAULT_NOISE_PP,
    DEFAULT_SEED, SoilState, advance_step, measure_moisture,
)


CSV_HEADER = (
    "run_id", "minute", "decision_moisture_percent", "previous_valve_open",
    "valve_open", "irrigation_minutes", "applied_water_l",
    "zone_1_before_percent", "zone_2_before_percent", "zone_3_before_percent",
    "zone_1_measured_percent", "zone_2_measured_percent", "zone_3_measured_percent",
    "zone_1_after_percent", "zone_2_after_percent", "zone_3_after_percent",
)


def wait_for_command(link: MqttLink, run_id: str, minute: int, timeout: float) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            command = link.receive(timeout=max(0.0, deadline - monotonic()))
        except Empty:
            break
        if (
            command.get("run_id") == run_id
            and type(command.get("minute")) is int
            and command["minute"] == minute
            and type(command.get("valve_open")) is bool
            and is_percent(command.get("decision_moisture_percent"))
        ):
            return command
    raise TimeoutError(f"No matching valve command for run {run_id}, minute {minute}")


def run_simulation(args, state: SoilState):
    run_id = uuid4().hex
    zones = (2,) if args.mode == "single" else (1, 2, 3)
    rng = Random(args.seed)
    previous = False
    irrigation_minutes = 0
    dry_minutes = [0, 0, 0]
    with MqttLink(args.host, args.port, COMMAND_TOPIC, args.timeout) as link:
        with args.output.open("w", newline="", encoding="utf-8") as output:
            log = csv.writer(output)
            log.writerow(CSV_HEADER)
            for _ in range(args.hours * 60 // STEP_MINUTES):
                before = state.moisture_percent
                measured = measure_moisture(state, rng, args.noise_pp)
                link.publish(MEASUREMENT_TOPIC, {
                    "run_id": run_id,
                    "minute": state.minute,
                    "valve_open": previous,
                    "moisture_percent": {str(zone): measured[zone - 1] for zone in zones},
                })
                command = wait_for_command(link, run_id, state.minute, args.timeout)
                step = advance_step(state, valve_open=command["valve_open"])
                log.writerow((
                    run_id, state.minute, command["decision_moisture_percent"], int(previous),
                    int(command["valve_open"]), step.irrigation_minutes, step.applied_water_l,
                    *before, *measured, *step.state.moisture_percent,
                ))
                for index, value in enumerate(before):
                    if value < args.dry_threshold:
                        dry_minutes[index] += STEP_MINUTES
                irrigation_minutes += step.irrigation_minutes
                previous = command["valve_open"]
                state = step.state
    return irrigation_minutes, tuple(dry_minutes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--mode", choices=("single", "average"), required=True)
    parser.add_argument("--hours", type=int, default=SIMULATION_HOURS)
    parser.add_argument("--timeout", type=float, default=5.0, help="MQTT timeout in seconds")
    parser.add_argument("--output", type=Path, default=Path("irrigation.csv"))
    parser.add_argument("--initial-water-mm", type=float, nargs=3, metavar="MM")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--noise-pp", type=float, default=DEFAULT_NOISE_PP,
                        help="Maximum sensor error in percentage points")
    parser.add_argument("--dry-threshold", type=float, default=40.0)
    args = parser.parse_args()
    if not 1 <= args.hours <= SIMULATION_HOURS:
        parser.error(f"--hours must be between 1 and {SIMULATION_HOURS}")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive number")
    if not is_percent(args.noise_pp) or not is_percent(args.dry_threshold):
        parser.error("Noise and dryness threshold must be between 0 and 100")
    try:
        state = SoilState() if args.initial_water_mm is None else SoilState(
            water_mm=tuple(args.initial_water_mm)
        )
    except ValueError as error:
        parser.error(str(error))

    try:
        irrigation_minutes, dry_minutes = run_simulation(args, state)
    except OSError as error:
        parser.exit(1, f"Simulator: {error}\n")
    water = irrigation_minutes * FLOW_L_PER_MIN
    print(f"Completed {args.hours} hours ({args.mode}), valve open {irrigation_minutes} min, "
          f"applied {water:g} L. Log: {args.output}")
    print(f"Dry hours below {args.dry_threshold:g}%: "
          + ", ".join(f"zone {i}: {minutes / 60:.3f}" for i, minutes in enumerate(dry_minutes, 1)))


if __name__ == "__main__":
    main()
