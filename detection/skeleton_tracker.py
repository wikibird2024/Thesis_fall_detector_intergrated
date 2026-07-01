
# skeleton_tracker.py
import cv2
import mediapipe as mp
import numpy as np


class SkeletonTracker:
    def __init__(self, model_complexity=1, min_detection_confidence=0.5, min_tracking_confidence=0.5):
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def track_from_box(self, frame, box):
        """
        Track skeleton landmarks within a bounding box.
        ROI is normalized to a square to avoid Mediapipe NORM_RECT warnings.
        Returns landmarks in frame coordinates: [x, y, z, visibility]
        """
        x1, y1, x2, y2 = map(int, box[:4])
        if x2 <= x1 or y2 <= y1:
            return []

        # Make ROI square
        width, height = x2 - x1, y2 - y1
        size = max(width, height)
        center_x, center_y = x1 + width // 2, y1 + height // 2
        half_size = size // 2

        x1_s = max(center_x - half_size, 0)
        y1_s = max(center_y - half_size, 0)
        x2_s = min(center_x + half_size, frame.shape[1])
        y2_s = min(center_y + half_size, frame.shape[0])

        crop = frame[y1_s:y2_s, x1_s:x2_s]
        if crop.size == 0:
            return []

        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        results = self.pose.process(crop_rgb)
        if not results.pose_landmarks:
            return []

        # Map landmarks back to original frame coordinates
        landmarks = []
        for lm in results.pose_landmarks.landmark:
            lx = int(lm.x * (x2_s - x1_s)) + x1_s
            ly = int(lm.y * (y2_s - y1_s)) + y1_s
            lz = lm.z
            visibility = lm.visibility
            landmarks.append([lx, ly, lz, visibility])

        return landmarks

    def close(self):
        self.pose.close()
