"""Core data types shared by every layer. No I/O, no framework imports."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# Detection box from HumanDetector: [x1, y1, x2, y2, confidence, class_id], pixels.
Box = Sequence[float]
# Pose landmark from SkeletonTracker: [x, y, z, visibility]; z is depth, not confidence.
Landmark = Sequence[float]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_event_id() -> str:
    """Short unique id. It appears in logs, alerts and the database, so one
    fall can be followed end to end (a "correlation id")."""
    return uuid.uuid4().hex[:12]


class EventSource(str, Enum):
    CAMERA = "camera"
    WEARABLE = "esp32"  # value kept as stored by version 1


class EventStatus(str, Enum):
    PENDING = "pending"  # saved, alert not finished yet
    ALERTED = "alerted"  # at least one alert channel delivered
    ALERT_FAILED = "alert_failed"  # every alert channel failed


@dataclass(frozen=True)
class FallEvent:
    source: EventSource
    entity_id: str  # "camera_person_<id>" or the wearable's device_id
    occurred_at: datetime = field(default_factory=utc_now)
    latitude: float | None = None
    longitude: float | None = None
    has_gps_fix: bool = False
    event_id: str = field(default_factory=new_event_id)

    @property
    def has_location(self) -> bool:
        return self.has_gps_fix and self.latitude is not None and self.longitude is not None

    def alert_text(self) -> str:
        """Human-readable alert, the same on every channel."""
        when = self.occurred_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if self.source is EventSource.CAMERA:
            head = f"⚠️ Fall detected by camera ({self.entity_id})"
        else:
            head = f"🚨 Fall detected by device {self.entity_id}"
        location = (
            f"GPS: {self.latitude}, {self.longitude} https://maps.google.com/?q={self.latitude},{self.longitude}"
            if self.has_location
            else "GPS: unknown"
        )
        return f"{head}\nTime: {when}\n{location}\nEvent: {self.event_id}"


@dataclass(frozen=True)
class Alert:
    event: FallEvent
    image_jpeg: bytes | None = None

    @property
    def message(self) -> str:
        return self.event.alert_text()
