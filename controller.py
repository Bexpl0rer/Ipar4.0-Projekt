"""Read MQTT measurements and publish a hysteretic shared valve decision."""

import argparse
from queue import Empty
from statistics import fmean

from mqtt_link import COMMAND_TOPIC, MEASUREMENT_TOPIC, MqttLink, is_percent
from soil_model import STEP_MINUTES, SIMULATION_MINUTES

DEFAULT_LOWER_THRESHOLD = 50.0
DEFAULT_UPPER_THRESHOLD = 60.0


def make_command(measurement: dict, lower_threshold=DEFAULT_LOWER_THRESHOLD,
                 upper_threshold=DEFAULT_UPPER_THRESHOLD):
    if not (is_percent(lower_threshold) and is_percent(upper_threshold)
            and lower_threshold < upper_threshold):
        raise ValueError("Thresholds must satisfy 0 <= lower < upper <= 100")
    run_id = measurement.get("run_id")
    minute = measurement.get("minute")
    moisture = measurement.get("moisture_percent")
    previous = measurement.get("valve_open")
    if (not isinstance(run_id, str) or not run_id or type(minute) is not int
            or not 0 <= minute < SIMULATION_MINUTES or minute % STEP_MINUTES
            or type(previous) is not bool):
        return None
    if not isinstance(moisture, dict) or moisture.keys() not in ({"2"}, {"1", "2", "3"}):
        return None
    if not all(is_percent(value) for value in moisture.values()):
        return None

    decision = round(fmean(moisture.values()), 6)
    # The previous applied valve state comes from the simulator. This makes
    # repeated MQTT messages idempotent and independent runs start cleanly.
    if decision <= lower_threshold:
        valve_open = True
    elif decision >= upper_threshold:
        valve_open = False
    else:
        valve_open = previous
    return {
        "run_id": run_id,
        "minute": minute,
        "decision_moisture_percent": decision,
        "valve_open": valve_open,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--lower-threshold", type=float, default=DEFAULT_LOWER_THRESHOLD)
    parser.add_argument("--upper-threshold", type=float, default=DEFAULT_UPPER_THRESHOLD)
    args = parser.parse_args()
    if not (is_percent(args.lower_threshold) and is_percent(args.upper_threshold)
            and args.lower_threshold < args.upper_threshold):
        parser.error("Thresholds must satisfy 0 <= lower < upper <= 100")

    try:
        with MqttLink(args.host, args.port, MEASUREMENT_TOPIC) as link:
            print(f"Listening on {MEASUREMENT_TOPIC} ({args.lower_threshold:g}%–{args.upper_threshold:g}%)", flush=True)
            while True:
                try:
                    measurement = link.receive(timeout=0.5)
                except Empty:
                    continue
                command = make_command(measurement, args.lower_threshold, args.upper_threshold)
                if command is not None:
                    link.publish(COMMAND_TOPIC, command)
    except KeyboardInterrupt:
        return
    except OSError as error:
        parser.exit(1, f"Controller: {error}\n")


if __name__ == "__main__":
    main()
