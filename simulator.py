"""Run the soil model through an MQTT controller and write an hourly CSV log."""

import argparse
import csv
import math
from pathlib import Path
from queue import Empty
from time import monotonic
from uuid import uuid4

from mqtt_link import COMMAND_TOPIC, MEASUREMENT_TOPIC, MqttLink, is_percent
from soil_model import SIMULATION_HOURS, SoilState, advance_hour


CSV_HEADER = (
    "run_id", "hour", "decision_moisture_percent", "valve_open", "applied_water_l",
    "zone_1_before_percent", "zone_2_before_percent", "zone_3_before_percent",
    "zone_1_after_percent", "zone_2_after_percent", "zone_3_after_percent",
)


def wait_for_command(link: MqttLink, run_id: str, hour: int, timeout: float) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            command = link.receive(timeout=max(0.0, deadline - monotonic()))
        except Empty:
            break
        if (
            command.get("run_id") == run_id
            and type(command.get("hour")) is int
            and command["hour"] == hour
            and type(command.get("valve_open")) is bool
            and is_percent(command.get("decision_moisture_percent"))
        ):
            return command
    raise TimeoutError(f"No matching valve command for run {run_id}, hour {hour}")


def run_simulation(args, state: SoilState) -> float:
    run_id = uuid4().hex
    zones = (2,) if args.mode == "single" else (1, 2, 3)
    total_water_l = 0.0
    with MqttLink(args.host, args.port, COMMAND_TOPIC, args.timeout) as link:
        with args.output.open("w", newline="", encoding="utf-8") as output:
            log = csv.writer(output)
            log.writerow(CSV_HEADER)
            for _ in range(args.hours):
                before = state.moisture_percent
                link.publish(MEASUREMENT_TOPIC, {
                    "run_id": run_id,
                    "hour": state.hour,
                    "moisture_percent": {str(zone): before[zone - 1] for zone in zones},
                })
                command = wait_for_command(link, run_id, state.hour, args.timeout)
                step = advance_hour(state, valve_open=command["valve_open"])
                log.writerow((
                    run_id, state.hour, command["decision_moisture_percent"],
                    int(command["valve_open"]), step.applied_water_l,
                    *before, *step.state.moisture_percent,
                ))
                total_water_l += step.applied_water_l
                state = step.state
    return total_water_l


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--mode", choices=("single", "average"), required=True)
    parser.add_argument("--hours", type=int, default=SIMULATION_HOURS)
    parser.add_argument("--timeout", type=float, default=5.0, help="MQTT timeout in seconds")
    parser.add_argument("--output", type=Path, default=Path("irrigation.csv"))
    parser.add_argument("--initial-water-mm", type=float, nargs=3, metavar="MM")
    args = parser.parse_args()
    if not 1 <= args.hours <= SIMULATION_HOURS:
        parser.error(f"--hours must be between 1 and {SIMULATION_HOURS}")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive number")
    try:
        state = SoilState() if args.initial_water_mm is None else SoilState(
            water_mm=tuple(args.initial_water_mm)
        )
    except ValueError as error:
        parser.error(str(error))

    try:
        water = run_simulation(args, state)
    except OSError as error:
        parser.exit(1, f"Simulator: {error}\n")
    print(f"Completed {args.hours} hours ({args.mode}), applied {water:g} L. Log: {args.output}")


if __name__ == "__main__":
    main()
