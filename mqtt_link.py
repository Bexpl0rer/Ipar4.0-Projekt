"""Connect a client and deliver JSON objects from one MQTT subscription."""

import json
from queue import Queue
from threading import Event

import paho.mqtt.client as mqtt


MEASUREMENT_TOPIC = "irrigation/measurement"
COMMAND_TOPIC = "irrigation/command"


def is_percent(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value <= 100


class MqttLink:
    def __init__(self, host: str, port: int, topic: str, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._topic = topic
        self._timeout = timeout
        self._ready = Event()
        self._startup_error = None
        self._messages = Queue()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.connect_timeout = timeout
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_message = self._on_message

    def __enter__(self):
        self._client.connect(self._host, self._port)
        self._client.loop_start()
        try:
            if not self._ready.wait(self._timeout):
                raise TimeoutError(f"No MQTT subscription acknowledgement for {self._topic}")
            if self._startup_error:
                raise ConnectionError(self._startup_error)
        except BaseException:
            self._close()
            raise
        return self

    def __exit__(self, *_):
        self._close()

    def _close(self):
        self._client.disconnect()
        self._client.loop_stop()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self._startup_error = f"MQTT connection failed: {reason_code}"
            self._ready.set()
            return
        result, _ = client.subscribe(self._topic, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._startup_error = f"MQTT subscribe failed: {mqtt.error_string(result)}"
            self._ready.set()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(reason.is_failure for reason in reason_codes):
            self._startup_error = f"Broker rejected MQTT subscription for {self._topic}"
        self._ready.set()

    def _on_message(self, client, userdata, message):
        if message.retain:
            return
        try:
            payload = json.loads(message.payload)
        except ValueError:
            return
        if isinstance(payload, dict):
            self._messages.put(payload)

    def publish(self, topic: str, payload: dict) -> None:
        result = self._client.publish(topic, json.dumps(payload), qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish failed: {mqtt.error_string(result.rc)}")

    def receive(self, timeout: float) -> dict:
        return self._messages.get(timeout=timeout)
