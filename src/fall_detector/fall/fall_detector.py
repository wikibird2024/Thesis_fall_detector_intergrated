"""Per-person fall decision from pose landmarks.

One FallDetector instance follows one person across frames. It confirms a fall
in two ways:

  active fall : torso tilted past the threshold AND moving fast,
                for `falling_frames` frames in a row
  lying state : torso tilted past threshold + margin (nearly horizontal),
                for `lying_frames` frames in a row

Geometry (image coordinates, y grows downward):

        shoulder mid  *            tilt =  0 deg  standing
                      |\\           tilt = 90 deg  lying
                      | \\ tilt     tilt = 180 deg upside down
        hip mid       *--

This module has no I/O and no config imports: it only needs FallThresholds,
which makes it easy to unit test and reuse.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fall_detector.domain import Landmark

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
KEY_POINTS = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP)
LANDMARK_COUNT = 33
VISIBILITY_INDEX = 3


@dataclass(frozen=True)
class FallThresholds:
    """Tuning values for FallDetector. Defaults match the original thesis values."""

    tilt_threshold_deg: float = 60.0  # torso tilt from vertical that counts as "not upright"
    lying_margin_deg: float = 10.0  # extra tilt on top of the threshold that counts as lying
    velocity_threshold_px: float = 0.5  # torso center movement per frame, in pixels
    falling_frames: int = 5  # frames in a row of "tilted and moving" to confirm
    lying_frames: int = 5  # frames in a row of "lying" to confirm
    min_visibility: float = 0.5  # shoulders and hips must be at least this visible


def torso_tilt_deg(landmarks: Sequence[Landmark]) -> float:
    """Angle between the hip->shoulder line and straight up, in degrees [0, 180]."""
    shoulder_x = (landmarks[LEFT_SHOULDER][0] + landmarks[RIGHT_SHOULDER][0]) / 2
    shoulder_y = (landmarks[LEFT_SHOULDER][1] + landmarks[RIGHT_SHOULDER][1]) / 2
    hip_x = (landmarks[LEFT_HIP][0] + landmarks[RIGHT_HIP][0]) / 2
    hip_y = (landmarks[LEFT_HIP][1] + landmarks[RIGHT_HIP][1]) / 2
    dx = shoulder_x - hip_x
    dy = shoulder_y - hip_y
    # "Up" in image coordinates is (0, -1), so -dy is the upward component.
    return math.degrees(math.atan2(abs(dx), -dy))


def torso_center(landmarks: Sequence[Landmark]) -> tuple[float, float]:
    x = sum(landmarks[i][0] for i in KEY_POINTS) / len(KEY_POINTS)
    y = sum(landmarks[i][1] for i in KEY_POINTS) / len(KEY_POINTS)
    return x, y


class FallDetector:
    """Stateful fall decision for one tracked person."""

    def __init__(self, thresholds: FallThresholds | None = None) -> None:
        self.thresholds = thresholds or FallThresholds()
        self.frames_falling = 0
        self.frames_lying = 0
        self.previous_center: tuple[float, float] | None = None

    def reset(self) -> None:
        """Clear state after a confirmed fall or when landmarks are unreliable."""
        self.frames_falling = 0
        self.frames_lying = 0
        self.previous_center = None

    def has_reliable_key_points(self, landmarks: Sequence[Landmark]) -> bool:
        if len(landmarks) < LANDMARK_COUNT:
            return False
        return all(
            len(landmarks[i]) > VISIBILITY_INDEX
            and landmarks[i][VISIBILITY_INDEX] >= self.thresholds.min_visibility
            for i in KEY_POINTS
        )

    def _speed_px(self, landmarks: Sequence[Landmark]) -> float:
        center = torso_center(landmarks)
        previous, self.previous_center = self.previous_center, center
        if previous is None:
            return 0.0
        return math.dist(center, previous)

    def detect_fall(self, landmarks: Sequence[Landmark]) -> bool:
        """Feed one frame. Returns True on the frame a fall is confirmed."""
        if not landmarks or not self.has_reliable_key_points(landmarks):
            self.reset()
            return False

        t = self.thresholds
        tilt = torso_tilt_deg(landmarks)
        speed = self._speed_px(landmarks)

        is_falling = tilt > t.tilt_threshold_deg and speed > t.velocity_threshold_px
        is_lying = tilt > t.tilt_threshold_deg + t.lying_margin_deg

        if is_falling:
            self.frames_falling += 1
            self.frames_lying = 0
        elif is_lying:
            self.frames_falling = 0
            self.frames_lying += 1
        else:
            self.frames_falling = 0
            self.frames_lying = 0

        confirmed = self.frames_falling >= t.falling_frames or self.frames_lying >= t.lying_frames
        if confirmed:
            self.reset()  # avoid firing again on the very next frame
        return confirmed
