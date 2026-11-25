"""Read MQTT measurements and publish a decision for the common valve."""

import argparse
from queue import Empty
from statistics import fmean

from mqtt_link import COMMAND_TOPIC, MEASUREMENT_TOPIC, MqttLink, is_percent


def make_command(measurement: dict, threshold: float):
    run_id = measurement.get("run_id")
    hour = measurement.get("hour")
    moisture = measurement.get("moisture_percent")
    if not isinstance(run_id, str) or not run_id or type(hour) is not int or hour < 0:
        return None
    if not isinstance(moisture, dict) or moisture.keys() not in ({"2"}, {"1", "2", "3"}):
        return None
    if not all(is_percent(value) for value in moisture.values()):
        return None

    # Stabilize equality at the threshold against float conversion and averaging.
    decision = round(fmean(moisture.values()), 6)
    return {
        "run_id": run_id,
        "hour": hour,
        "decision_moisture_percent": decision,
        "valve_open": decision < threshold,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--threshold", type=float, default=50.0)
    args = parser.parse_args()
    if not is_percent(args.threshold):
        parser.error("--threshold must be between 0 and 100")

    try:
        with MqttLink(args.host, args.port, MEASUREMENT_TOPIC) as link:
            print(f"Listening on {MEASUREMENT_TOPIC} (threshold {args.threshold:g}%)", flush=True)
            while True:
                try:
                    measurement = link.receive(timeout=0.5)
                except Empty:
                    continue
                command = make_command(measurement, args.threshold)
                if command is not None:
                    link.publish(COMMAND_TOPIC, command)
    except KeyboardInterrupt:
        return
    except OSError as error:
        parser.exit(1, f"Controller: {error}\n")


if __name__ == "__main__":
    main()
