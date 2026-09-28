"""Turns camera detections and wearable messages into fall events.

    camera person --> FallDetector (per person) --+
                                                   +--> cooldown / dedup --> AlertSink.submit()
    wearable msg  --> fall_detected == true -------+

This class makes decisions only. It does no network or disk I/O, so every
method is synchronous, fast, and easy to test with a fake clock and a fake sink.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable, Sequence
from typing import Protocol

import numpy as np

from fall_detector.domain import Box, EventSource, FallEvent, Landmark, utc_now
from fall_detector.fall.fall_detector import FallDetector, FallThresholds
from fall_detector.inputs.mqtt_client import DeviceFallMessage
from fall_detector.observability import metrics
from fall_detector.vision.drawing import fall_snapshot

logger = logging.getLogger(__name__)

RECENT_TIMESTAMPS_PER_DEVICE = 32  # enough to catch MQTT re-deliveries


class AlertSink(Protocol):
    def submit(self, event: FallEvent, image_jpeg: bytes | None = None) -> bool: ...


def camera_entity_id(person_id: int) -> str:
    return f"camera_person_{person_id}"


class DetectionProcessor:
    def __init__(
        self,
        alerts: AlertSink,
        *,
        thresholds: FallThresholds | None = None,
        cooldown_s: float = 60.0,
        forget_after_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.alerts = alerts
        self.thresholds = thresholds or FallThresholds()
        self.cooldown_s = cooldown_s
        # Never forget an entity while its cooldown still runs, or a device that
        # re-sends every 40 s would get a fresh alert each time.
        self.forget_after_s = max(forget_after_s, cooldown_s)
        self._clock = clock

        self.fall_detectors: dict[str, FallDetector] = {}
        self.last_alert_at: dict[str, float] = {}
        self.last_seen_at: dict[str, float] = {}
        self.recent_device_timestamps: dict[str, deque[float]] = {}

    # ------------------------------------------------------------------ inputs

    def handle_camera_data(
        self, frame: np.ndarray | None, person_id: int, box: Box, landmarks: Sequence[Landmark]
    ) -> bool:
        """Feed one tracked person from one frame. Returns True if a fall is confirmed now."""
        entity_id = camera_entity_id(person_id)
        self.last_seen_at[entity_id] = self._clock()
        detector = self.fall_detectors.get(entity_id)
        if detector is None:
            detector = self.fall_detectors[entity_id] = FallDetector(self.thresholds)

        if not detector.detect_fall(landmarks):
            return False

        metrics.FALLS_DETECTED.labels(source=EventSource.CAMERA.value).inc()
        if self._cooldown_active(entity_id):
            return True
        event = FallEvent(source=EventSource.CAMERA, entity_id=entity_id)
        image = fall_snapshot(frame, box, landmarks, entity_id) if frame is not None else None
        self._raise_alarm(event, image)
        return True

    def handle_mqtt_data(self, message: DeviceFallMessage) -> bool:
        """Feed one validated wearable message. Returns True if an alert was raised."""
        device_id = message.device_id
        self.last_seen_at[device_id] = self._clock()
        if not message.fall_detected:
            return False

        metrics.FALLS_DETECTED.labels(source=EventSource.WEARABLE.value).inc()
        if message.timestamp is not None and self._is_duplicate(device_id, message.timestamp):
            logger.info("Duplicate message from %s (timestamp %s) ignored", device_id, message.timestamp)
            metrics.ALERTS_SUPPRESSED.labels(reason="duplicate").inc()
            return False
        if self._cooldown_active(device_id):
            return False

        event = FallEvent(
            source=EventSource.WEARABLE,
            entity_id=device_id,
            occurred_at=utc_now(),
            latitude=message.latitude,
            longitude=message.longitude,
            has_gps_fix=message.has_gps_fix,
        )
        self._raise_alarm(event, None)
        return True

    # ------------------------------------------------------------------ rules

    def _is_duplicate(self, device_id: str, timestamp: float) -> bool:
        seen = self.recent_device_timestamps.setdefault(device_id, deque(maxlen=RECENT_TIMESTAMPS_PER_DEVICE))
        if timestamp in seen:
            return True
        seen.append(timestamp)
        return False

    def _cooldown_active(self, entity_id: str) -> bool:
        last = self.last_alert_at.get(entity_id)
        if last is not None and self._clock() - last < self.cooldown_s:
            logger.info("Fall for %s not alerted: cooldown (%.0fs) active", entity_id, self.cooldown_s)
            metrics.ALERTS_SUPPRESSED.labels(reason="cooldown").inc()
            return True
        return False

    def _raise_alarm(self, event: FallEvent, image_jpeg: bytes | None) -> None:
        self.last_alert_at[event.entity_id] = self._clock()
        self.alerts.submit(event, image_jpeg)

    # ------------------------------------------------------------------ housekeeping

    def evict_stale(self) -> list[str]:
        """Forget people/devices not seen for `forget_after_s`. Returns the ids removed."""
        now = self._clock()
        stale = [eid for eid, seen in self.last_seen_at.items() if now - seen > self.forget_after_s]
        for entity_id in stale:
            self.fall_detectors.pop(entity_id, None)
            self.last_alert_at.pop(entity_id, None)
            self.last_seen_at.pop(entity_id, None)
            self.recent_device_timestamps.pop(entity_id, None)
        if stale:
            logger.debug("Forgot stale entities: %s", stale)
        return stale
