"""One frame in, tracked people with skeletons out.

    frame --> HumanDetector (YOLO) --> PersonTracker (ids) --> SkeletonTracker (pose, per person)

The camera pipeline depends on the FrameAnalyzer protocol, not on YOLO or
MediaPipe, so tests can plug in a fake analyzer and run without any model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from fall_detector.domain import Box, Landmark
from fall_detector.vision.human_detector import HumanDetector
from fall_detector.vision.person_tracker import PersonTracker
from fall_detector.vision.skeleton_tracker import SkeletonTracker


@dataclass(frozen=True)
class TrackedPerson:
    person_id: int
    box: Box
    landmarks: list[Landmark] = field(default_factory=list)


class FrameAnalyzer(Protocol):
    def analyze(self, frame: np.ndarray) -> list[TrackedPerson]: ...

    def close(self) -> None: ...


class PoseFrameAnalyzer:
    """Blocking (CPU/GPU heavy): call it with asyncio.to_thread()."""

    def __init__(self, detector: HumanDetector, tracker: PersonTracker, skeleton: SkeletonTracker) -> None:
        self.detector = detector
        self.tracker = tracker
        self.skeleton = skeleton

    def analyze(self, frame: np.ndarray) -> list[TrackedPerson]:
        boxes = self.detector.detect_humans(frame)
        return [
            TrackedPerson(person_id, box, self.skeleton.track_from_box(frame, box))
            for person_id, box in self.tracker.update(boxes)
        ]

    def close(self) -> None:
        self.skeleton.close()
