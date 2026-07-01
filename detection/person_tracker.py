import numpy as np


class PersonTracker:
    def __init__(self, iou_threshold=0.3):
        self.next_id = 0
        self.tracked_people = {}  # {person_id: bounding_box}
        self.iou_threshold = iou_threshold

    def _calculate_iou(self, box1, box2):
        """Calculates Intersection over Union (IoU) of two bounding boxes."""
        x1_i = max(box1[0], box2[0])
        y1_i = max(box1[1], box2[1])
        x2_i = min(box1[2], box2[2])
        y2_i = min(box1[3], box2[3])

        intersection_area = max(0, x2_i - x1_i) * max(0, y2_i - y1_i)

        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

        union_area = box1_area + box2_area - intersection_area
        if union_area == 0:
            return 0
        return intersection_area / union_area

    def update(self, detected_boxes):
        """
        Updates tracked people with new detections.

        Args:
            detected_boxes (list): List of new bounding boxes [x1, y1, x2, y2, conf, cls].

        Returns:
            list: A list of (person_id, box) for all currently tracked people.
        """
        current_tracked = {}
        matched_indices = set()

        # Match each existing track to the best (highest IoU) unmatched detection
        for person_id, old_box in self.tracked_people.items():
            best_iou = self.iou_threshold
            best_idx = -1
            for i, new_box in enumerate(detected_boxes):
                if i in matched_indices:
                    continue
                iou = self._calculate_iou(old_box[:4], new_box[:4])
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i
            if best_idx >= 0:
                current_tracked[person_id] = detected_boxes[best_idx]
                matched_indices.add(best_idx)

        # Any unmatched detection is a new person
        for i, new_box in enumerate(detected_boxes):
            if i not in matched_indices:
                current_tracked[self.next_id] = new_box
                self.next_id += 1

        self.tracked_people = current_tracked
        return list(self.tracked_people.items())
