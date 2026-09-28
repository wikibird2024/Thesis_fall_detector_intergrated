"""Person detection with YOLOv8."""

from __future__ import annotations

import numpy as np

from fall_detector.domain import Box

PERSON_CLASS_ID = 0  # COCO class 0 = person


class HumanDetector:
    def __init__(
        self, model_path: str = "yolov8n.pt", conf_threshold: float = 0.5, iou_threshold: float = 0.7
    ):
        # Imported here: ultralytics pulls in torch (~1 GB). Tests and tools that
        # never detect people should not pay for it.
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

    def detect_humans(self, frame: np.ndarray) -> list[Box]:
        """Returns [x1, y1, x2, y2, confidence, class_id] for each person found."""
        result = self.model.predict(
            frame, conf=self.conf_threshold, iou=self.iou_threshold, classes=[PERSON_CLASS_ID], verbose=False
        )[0]
        if result.boxes is None or result.boxes.xyxy is None:
            return []
        boxes = result.boxes.xyxy.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()
        classes = result.boxes.cls.cpu().numpy().astype(int)
        return [
            [*map(int, xyxy), float(confidence), int(class_id)]
            for xyxy, confidence, class_id in zip(boxes, confidences, classes, strict=True)
            if class_id == PERSON_CLASS_ID
        ]
