"""DetectionProcessor: turns detections into fall events, applies cooldown and dedup, fires alerts.

Real Telegram/Asterisk/database are replaced with fakes so the tests are fast
and run without network.
"""

import asyncio

import numpy as np
import pytest

from fall_detector.processing import detection_processor as module
from fall_detector.processing.detection_processor import DetectionProcessor


class FakeAmi:
    def __init__(self):
        self.messages: list[str] = []

    async def alert_devices(self, message):
        self.messages.append(message)


class FakeTelegram:
    def __init__(self):
        self.messages: list[str] = []
        self.photos: list[str] = []

    async def send_message(self, text):
        self.messages.append(text)

    async def send_photo(self, frame, caption=""):
        self.photos.append(caption)


class AlwaysFall:
    def detect_fall(self, landmarks):
        return True


@pytest.fixture
def saved_events(monkeypatch):
    events = []

    def fake_insert(event):
        events.append(event)
        return len(events)

    monkeypatch.setattr(module, "insert_fall_event", fake_insert)
    return events


@pytest.fixture
def processor(saved_events):
    return DetectionProcessor(FakeAmi(), FakeTelegram())


def mqtt_message(**overrides):
    message = {
        "device_id": "wrist-01",
        "fall_detected": True,
        "timestamp": 1_700_000_000,
        "latitude": 10.77,
        "longitude": 106.70,
        "has_gps_fix": True,
    }
    message.update(overrides)
    return message


FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
BOX = [100, 100, 200, 300, 0.9, 0]


async def test_camera_fall_saves_event_and_alerts_both_channels(processor, saved_events):
    processor.fall_detectors["camera_person_7"] = AlwaysFall()

    await processor.handle_camera_data(FRAME, 7, BOX, landmarks=[])

    assert len(saved_events) == 1
    assert saved_events[0]["source"] == "camera"
    assert len(processor.ami_trigger.messages) == 1
    assert len(processor.telegram_bot.photos) == 1


async def test_second_camera_fall_within_cooldown_is_not_alerted(processor, saved_events):
    processor.fall_detectors["camera_person_7"] = AlwaysFall()

    await processor.handle_camera_data(FRAME, 7, BOX, landmarks=[])
    await processor.handle_camera_data(FRAME, 7, BOX, landmarks=[])

    assert len(saved_events) == 1
    assert len(processor.ami_trigger.messages) == 1


async def test_mqtt_fall_is_alerted_with_gps_in_message(processor, saved_events):
    await processor.handle_mqtt_data(mqtt_message())

    assert saved_events[0]["entity_id"] == "wrist-01"
    assert "10.77, 106.7" in processor.telegram_bot.messages[0]


async def test_mqtt_duplicate_timestamp_is_ignored(processor, saved_events):
    processor.cooldown_minutes = 0  # isolate dedup from cooldown
    await processor.handle_mqtt_data(mqtt_message())
    await processor.handle_mqtt_data(mqtt_message())

    assert len(saved_events) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"fall_detected": False},
        {"device_id": ""},
        {"timestamp": None},
        {"latitude": 123.0},
        {"longitude": "east"},
    ],
    ids=["not-a-fall", "no-device", "no-timestamp", "latitude-out-of-range", "longitude-not-number"],
)
async def test_invalid_mqtt_messages_are_dropped(processor, saved_events, overrides):
    await processor.handle_mqtt_data(mqtt_message(**overrides))
    assert saved_events == []


async def test_mqtt_json_string_is_accepted(processor, saved_events):
    await processor.handle_mqtt_data('{"device_id": "d1", "fall_detected": true, "timestamp": 5}')
    assert len(saved_events) == 1


async def test_stale_entities_are_evicted(processor):
    processor.fall_detectors["camera_person_1"] = AlwaysFall()
    await processor.handle_camera_data(FRAME, 1, BOX, landmarks=[])

    processor.evict_stale_detectors(max_age_seconds=-1)

    assert processor.fall_detectors == {}
    assert processor.last_alert_timestamps == {}


@pytest.mark.xfail(strict=True, reason="bug: a failed database write stops the alert from being sent")
async def test_alert_is_still_sent_when_database_fails(monkeypatch):
    def broken_insert(event):
        raise OSError("disk full")

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(module, "insert_fall_event", broken_insert)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    processor = DetectionProcessor(FakeAmi(), FakeTelegram())

    await processor.handle_mqtt_data(mqtt_message())

    assert processor.ami_trigger.messages, "fall happened but nobody was alerted"
