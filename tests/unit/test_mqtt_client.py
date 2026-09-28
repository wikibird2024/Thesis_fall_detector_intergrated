"""MQTTClient: turns raw broker payloads into normalized dicts on a queue."""

import json
from types import SimpleNamespace

import pytest

from fall_detector.inputs.mqtt_client import MQTTClient


def raw_message(payload) -> SimpleNamespace:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return SimpleNamespace(payload=body, topic="tranhao/feeds/fall_alert")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(True, True), ("true", True), ("YES", True), ("1", True), (1, True), ("false", False), (0, False),
     (None, False)],
)
def test_to_bool_accepts_common_spellings(raw, expected):
    assert MQTTClient._to_bool(raw) is expected


async def test_valid_payload_is_normalized_and_queued():
    client = MQTTClient()
    await client._process_message(raw_message({"device_id": "d1", "fall_detected": "true", "latitude": "10.5"}))

    queued = client.message_queue.get_nowait()
    assert queued["device_id"] == "d1"
    assert queued["fall_detected"] is True
    assert queued["latitude"] == 10.5


async def test_invalid_json_is_dropped():
    client = MQTTClient()
    await client._process_message(raw_message(b"not json {"))
    assert client.message_queue.empty()
