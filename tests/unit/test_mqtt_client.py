"""MQTT input: payload contract and the reconnect loop."""

import asyncio
import json

import aiomqtt
import pytest

from fakes import wait_until
from fall_detector.inputs.mqtt_client import DeviceFallMessage, MQTTClient, parse_payload


def payload(**fields) -> bytes:
    data = {"device_id": "wrist-01", "fall_detected": True}
    data.update(fields)
    return json.dumps(data).encode()


# ---------------------------------------------------------------- contract


@pytest.mark.parametrize("raw", [True, "true", "YES", "1", 1, "on"])
def test_fall_detected_accepts_common_true_spellings(raw):
    assert parse_payload(payload(fall_detected=raw)).fall_detected is True


@pytest.mark.parametrize("raw", [False, "false", "no", "0", 0])
def test_fall_detected_accepts_common_false_spellings(raw):
    assert parse_payload(payload(fall_detected=raw)).fall_detected is False


def test_valid_location_is_kept():
    message = parse_payload(payload(latitude="10.5", longitude=106.7, has_gps_fix=True))
    assert (message.latitude, message.longitude, message.has_gps_fix) == (10.5, 106.7, True)


@pytest.mark.parametrize(
    "location",
    [{"latitude": 123.0, "longitude": 5}, {"latitude": "north", "longitude": 5}, {"latitude": 10}],
    ids=["out-of-range", "not-a-number", "half-missing"],
)
def test_unusable_location_becomes_unknown_but_message_is_kept(location):
    message = parse_payload(payload(has_gps_fix=True, **location))
    assert message.fall_detected
    assert (message.latitude, message.longitude, message.has_gps_fix) == (None, None, False)


@pytest.mark.parametrize(
    "raw",
    [b"not json {", b"[1, 2]", json.dumps({"fall_detected": True}).encode(), payload(device_id="")],
    ids=["not-json", "not-an-object", "no-device-id", "empty-device-id"],
)
def test_invalid_payload_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_payload(raw)


def test_handle_payload_queues_valid_and_drops_invalid():
    client = MQTTClient("broker", 1883, "topic")
    client.handle_payload(payload())
    client.handle_payload(b"garbage")
    assert client.messages.qsize() == 1
    assert isinstance(client.messages.get_nowait(), DeviceFallMessage)


def test_full_queue_drops_without_raising():
    client = MQTTClient("broker", 1883, "topic", queue_size=1)
    client.handle_payload(payload())
    client.handle_payload(payload())
    assert client.messages.qsize() == 1


# ---------------------------------------------------------------- reconnect loop


class FakeMqttConnection:
    """Mimics `async with aiomqtt.Client(...) as client`. Fails the first `failures` connects."""

    attempts = 0

    def __init__(self, failures: int, payloads: list[bytes]):
        self.failures = failures
        self.payloads = payloads

    def __call__(self, **kwargs):
        FakeMqttConnection.attempts += 1
        return self

    async def __aenter__(self):
        if FakeMqttConnection.attempts <= self.failures:
            raise aiomqtt.MqttError("connection refused")
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic, qos=0):
        self.subscribed = topic

    @property
    def messages(self):
        async def stream():
            for body in self.payloads:
                yield type("Message", (), {"payload": body})()
            await asyncio.Event().wait()  # stay connected

        return stream()


async def test_client_keeps_reconnecting_until_broker_is_back():
    FakeMqttConnection.attempts = 0
    connection = FakeMqttConnection(failures=3, payloads=[payload()])
    client = MQTTClient(
        "broker", 1883, "topic", reconnect_min_s=0.001, reconnect_max_s=0.001, client_factory=connection
    )
    task = asyncio.create_task(client.run_forever())
    try:
        await wait_until(lambda: client.messages.qsize() == 1)
        assert client.is_connected
        assert FakeMqttConnection.attempts == 4
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not client.is_connected
