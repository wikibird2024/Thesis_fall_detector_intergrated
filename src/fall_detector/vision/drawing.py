"""Drawing boxes/skeletons on frames and encoding snapshots for alerts."""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from fall_detector.domain import Box, Landmark

# Colors are BGR (OpenCV order).
NORMAL_COLOR = (0, 255, 0)
FALL_COLOR = (0, 0, 255)
SKELETON_LINE_COLOR = (0, 0, 255)
SKELETON_POINT_COLOR = (255, 0, 0)
BOX_THICKNESS = 2
LINE_THICKNESS = 2
POINT_RADIUS = 4
MIN_VISIBILITY = 0.5

# Same pairs as mediapipe.solutions.pose.POSE_CONNECTIONS, copied so drawing
# does not need the MediaPipe package (checked by tests/unit/test_drawing.py).
POSE_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
)  # fmt: skip


def draw_person(
    frame: np.ndarray, box: Box, landmarks: Sequence[Landmark], label: str, is_fall: bool
) -> None:
    """Draw box, label and skeleton in place."""
    color = FALL_COLOR if is_fall else NORMAL_COLOR
    x1, y1, x2, y2 = (int(v) for v in box[:4])
    confidence = box[4] if len(box) > 4 else 0.0
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, BOX_THICKNESS)
    text = f"{label} | {'FALL' if is_fall else 'ok'} | {confidence:.2f}"
    cv2.putText(frame, text, (x1, max(y1 - 10, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    draw_skeleton(frame, landmarks)


def draw_skeleton(frame: np.ndarray, landmarks: Sequence[Landmark]) -> None:
    def visible(point: Landmark) -> bool:
        return len(point) > 3 and point[3] > MIN_VISIBILITY

    for start, end in POSE_CONNECTIONS:
        if end < len(landmarks) and visible(landmarks[start]) and visible(landmarks[end]):
            a, b = landmarks[start], landmarks[end]
            cv2.line(
                frame, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), SKELETON_LINE_COLOR, LINE_THICKNESS
            )
    for point in landmarks:
        if visible(point):
            cv2.circle(frame, (int(point[0]), int(point[1])), POINT_RADIUS, SKELETON_POINT_COLOR, -1)


def encode_jpeg(frame: np.ndarray, max_side_px: int = 1080, quality: int = 80) -> bytes | None:
    """Downscale if needed and encode as JPEG. Returns None for an unusable frame."""
    if not isinstance(frame, np.ndarray) or frame.ndim < 2 or min(frame.shape[:2]) < 10:
        return None
    largest = max(frame.shape[:2])
    if largest > max_side_px:
        scale = max_side_px / largest
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buffer.tobytes() if ok else None


def fall_snapshot(frame: np.ndarray, box: Box, landmarks: Sequence[Landmark], label: str) -> bytes | None:
    """JPEG of the frame with the fallen person marked. Does not change `frame`."""
    if not isinstance(frame, np.ndarray):
        return None
    copy = frame.copy()
    draw_person(copy, box, landmarks, label, is_fall=True)
    return encode_jpeg(copy)
