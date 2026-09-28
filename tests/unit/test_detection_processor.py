"""DetectionProcessor: turns detections into fall events; applies cooldown and dedup.

The processor only decides. A RecordingSink stands in for the alert dispatcher
and a FakeClock controls time, so no test sleeps.
"""

import numpy as np
import pytest

from builders import box, lying, standing
from fakes import FakeClock, RecordingSink
from fall_detector.domain import EventSource
from fall_detector.fall.fall_detector import FallThresholds
from fall_detector.inputs.mqtt_client import DeviceFallMessage
from fall_detector.processing.detection_processor import DetectionProcessor

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
BOX = box(100, 100, 200, 300)
ONE_FRAME = FallThresholds(lying_frames=1, falling_frames=1)  # every lying frame is a fall


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sink():
    return RecordingSink()


@pytest.fixture
def processor(sink, clock):
    return DetectionProcessor(sink, thresholds=ONE_FRAME, cooldown_s=60, forget_after_s=30, clock=clock)


def wearable(**overrides) -> DeviceFallMessage:
    values = dict(
        device_id="wrist-01",
        fall_detected=True,
        timestamp=1_700_000_000,
        latitude=10.77,
        longitude=106.70,
        has_gps_fix=True,
    )
    values.update(overrides)
    return DeviceFallMessage(**values)


# ---------------------------------------------------------------- camera


def test_camera_fall_submits_event_with_snapshot(processor, sink):
    assert processor.handle_camera_data(FRAME, 7, BOX, lying())

    [event] = sink.events
    assert event.source is EventSource.CAMERA
    assert event.entity_id == "camera_person_7"
    assert sink.images[0].startswith(b"\xff\xd8")  # JPEG


def test_standing_person_submits_nothing(processor, sink):
    assert not processor.handle_camera_data(FRAME, 7, BOX, standing())
    assert sink.events == []


def test_each_person_has_own_fall_state(sink, clock):
    processor = DetectionProcessor(sink, thresholds=FallThresholds(lying_frames=2), clock=clock)
    processor.handle_camera_data(FRAME, 1, BOX, lying())
    processor.handle_camera_data(FRAME, 2, BOX, lying())
    assert sink.events == []  # one lying frame each: not enough yet
    processor.handle_camera_data(FRAME, 1, BOX, lying())
    assert [e.entity_id for e in sink.events] == ["camera_person_1"]


def test_cooldown_blocks_repeat_alert_then_expires(processor, sink, clock):
    processor.handle_camera_data(FRAME, 7, BOX, lying())
    clock.advance(59)
    assert processor.handle_camera_data(FRAME, 7, BOX, lying())  # still a fall...
    assert len(sink.events) == 1  # ...but not alerted again

    clock.advance(2)
    processor.handle_camera_data(FRAME, 7, BOX, lying())
    assert len(sink.events) == 2


def test_missing_frame_still_alerts_without_image(processor, sink):
    processor.handle_camera_data(None, 7, BOX, lying())
    assert sink.images == [None]


# ---------------------------------------------------------------- wearable


def test_wearable_fall_submits_event_with_location(processor, sink):
    assert processor.handle_mqtt_data(wearable())

    [event] = sink.events
    assert event.source is EventSource.WEARABLE
    assert (event.latitude, event.longitude, event.has_location) == (10.77, 106.70, True)
    assert "10.77, 106.7" in event.alert_text()


def test_wearable_message_without_fall_is_ignored(processor, sink):
    assert not processor.handle_mqtt_data(wearable(fall_detected=False))
    assert sink.events == []


def test_duplicate_delivery_is_ignored_even_after_cooldown(processor, sink, clock):
    processor.handle_mqtt_data(wearable(timestamp=1))
    clock.advance(120)
    processor.handle_mqtt_data(wearable(timestamp=1))  # broker re-delivered the same message
    assert len(sink.events) == 1


def test_older_redelivery_is_also_caught(processor, sink, clock):
    processor.cooldown_s = 0
    for ts in (1, 2, 1):
        processor.handle_mqtt_data(wearable(timestamp=ts))
    assert len(sink.events) == 2


def test_new_fall_after_cooldown_is_alerted(processor, sink, clock):
    processor.handle_mqtt_data(wearable(timestamp=1))
    clock.advance(61)
    processor.handle_mqtt_data(wearable(timestamp=2))
    assert len(sink.events) == 2


def test_message_without_timestamp_is_still_alerted(processor, sink):
    # Safety first: without a timestamp we can't dedup, but a fall is still a fall.
    assert processor.handle_mqtt_data(wearable(timestamp=None))


# ---------------------------------------------------------------- housekeeping


def test_stale_entities_are_forgotten(processor, clock):
    processor.handle_camera_data(FRAME, 1, BOX, standing())
    clock.advance(61)  # past forget_after_s AND cooldown
    assert processor.evict_stale() == ["camera_person_1"]
    assert processor.fall_detectors == {}


def test_entity_is_not_forgotten_while_cooldown_runs(sink, clock):
    # Regression: eviction after 30 s wiped the 60 s cooldown, so a device
    # re-sending every 40 s got a new alert every time.
    processor = DetectionProcessor(sink, cooldown_s=60, forget_after_s=30, clock=clock)
    processor.handle_mqtt_data(wearable(timestamp=1))
    clock.advance(40)
    processor.evict_stale()
    processor.handle_mqtt_data(wearable(timestamp=2))
    assert len(sink.events) == 1
