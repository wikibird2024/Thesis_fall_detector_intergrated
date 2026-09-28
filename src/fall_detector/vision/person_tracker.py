"""Gives each detected person a stable id from frame to frame (IoU matching).

Simple greedy tracker: each existing track takes the unmatched detection with
the highest overlap above `iou_threshold`; leftover detections become new people.
A person missing for one frame gets a new id when they come back.
(ByteTrack would fix that; see docs/ROADMAP.md, phase 6.)
"""

from __future__ import annotations

from collections.abc import Sequence

from fall_detector.domain import Box


def iou(a: Box, b: Box) -> float:
    """Intersection over union of two [x1, y1, x2, y2, ...] boxes, 0..1."""
    overlap_w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    overlap_h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = overlap_w * overlap_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


class PersonTracker:
    def __init__(self, iou_threshold: float = 0.3) -> None:
        self.iou_threshold = iou_threshold
        self.next_id = 0
        self.tracked_people: dict[int, Box] = {}

    def update(self, detected_boxes: Sequence[Box]) -> list[tuple[int, Box]]:
        """Match this frame's boxes to known people. Returns (person_id, box) pairs."""
        current: dict[int, Box] = {}
        matched: set[int] = set()

        for person_id, old_box in self.tracked_people.items():
            best_iou, best_index = self.iou_threshold, -1
            for index, new_box in enumerate(detected_boxes):
                if index in matched:
                    continue
                overlap = iou(old_box, new_box)
                if overlap > best_iou:
                    best_iou, best_index = overlap, index
            if best_index >= 0:
                current[person_id] = detected_boxes[best_index]
                matched.add(best_index)

        for index, new_box in enumerate(detected_boxes):
            if index not in matched:
                current[self.next_id] = new_box
                self.next_id += 1

        self.tracked_people = current
        return list(current.items())
