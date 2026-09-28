"""Small factories for test data. Keep tests short and readable.

Image coordinates: x grows to the right, y grows DOWNWARD (OpenCV/MediaPipe).
Landmarks follow SkeletonTracker output: [x, y, z, visibility].
"""

from __future__ import annotations

import math

LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP = 11, 12, 23, 24
LANDMARK_COUNT = 33


def make_landmarks(
    shoulder_center: tuple[float, float],
    hip_center: tuple[float, float],
    half_width: float = 20.0,
    visibility: float = 0.9,
    depth: float = -0.2,
) -> list[list[float]]:
    """Build 33 MediaPipe-style landmarks with a torso between the two centers.

    `depth` is MediaPipe's z value. Real z is usually small or negative, which
    is why it must never be read as a confidence value.
    """
    landmarks = [[0.0, 0.0, depth, visibility] for _ in range(LANDMARK_COUNT)]
    sx, sy = shoulder_center
    hx, hy = hip_center
    # Shoulders/hips spread perpendicular to the torso line.
    angle = math.atan2(hy - sy, hx - sx)
    ox, oy = -math.sin(angle) * half_width, math.cos(angle) * half_width
    landmarks[LEFT_SHOULDER] = [sx + ox, sy + oy, depth, visibility]
    landmarks[RIGHT_SHOULDER] = [sx - ox, sy - oy, depth, visibility]
    landmarks[LEFT_HIP] = [hx + ox, hy + oy, depth, visibility]
    landmarks[RIGHT_HIP] = [hx - ox, hy - oy, depth, visibility]
    return landmarks


def standing(x: float = 320.0, top: float = 100.0, bottom: float = 300.0, **kwargs) -> list[list[float]]:
    """Upright torso: shoulders straight above hips."""
    return make_landmarks((x, top), (x, bottom), **kwargs)


def lying(y: float = 400.0, left: float = 200.0, right: float = 400.0, **kwargs) -> list[list[float]]:
    """Horizontal torso: shoulders and hips at the same height."""
    return make_landmarks((left, y), (right, y), **kwargs)


def tilted(
    angle_from_vertical_deg: float, hip: tuple[float, float] = (320.0, 300.0), length: float = 200.0, **kwargs
) -> list[list[float]]:
    """Torso rotated away from vertical by the given angle, pivoting on the hips."""
    rad = math.radians(angle_from_vertical_deg)
    shoulder = (hip[0] + math.sin(rad) * length, hip[1] - math.cos(rad) * length)
    return make_landmarks(shoulder, hip, **kwargs)


def box(x1: int, y1: int, x2: int, y2: int, confidence: float = 0.9) -> list:
    """Detection box in HumanDetector format: [x1, y1, x2, y2, confidence, class_id]."""
    return [x1, y1, x2, y2, confidence, 0]
