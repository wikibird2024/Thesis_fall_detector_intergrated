"""Pose landmarks for one person with MediaPipe Pose."""

from __future__ import annotations

import cv2
import numpy as np

from fall_detector.domain import Box, Landmark


class SkeletonTracker:
    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        import mediapipe as mp  # heavy import, only when pose is really needed

        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def track_from_box(self, frame: np.ndarray, box: Box) -> list[Landmark]:
        """Landmarks [x, y, z, visibility] in frame pixels, or [] if no pose found.

        The crop is made square around the box to avoid MediaPipe NORM_RECT warnings.
        """
        x1, y1, x2, y2 = (int(v) for v in box[:4])
        if x2 <= x1 or y2 <= y1:
            return []

        width, height = x2 - x1, y2 - y1
        half_size = max(width, height) // 2
        center_x, center_y = x1 + width // 2, y1 + height // 2
        left = max(center_x - half_size, 0)
        top = max(center_y - half_size, 0)
        right = min(center_x + half_size, frame.shape[1])
        bottom = min(center_y + half_size, frame.shape[0])

        crop = frame[top:bottom, left:right]
        if crop.size == 0:
            return []
        results = self.pose.process(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return []

        crop_w, crop_h = right - left, bottom - top
        return [
            [int(lm.x * crop_w) + left, int(lm.y * crop_h) + top, lm.z, lm.visibility]
            for lm in results.pose_landmarks.landmark
        ]

    def close(self) -> None:
        self.pose.close()
