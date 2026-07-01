import numpy as np


class PersonTracker:
    def __init__(self, iou_threshold=0.3):
        self.next_id = 0
        self.tracked_people = {}  # Stores {person_id: bounding_box}
        self.iou_threshold = iou_threshold

    def _calculate_iou(self, box1, box2):
        """Calculates Intersection over Union (IoU) of two bounding boxes."""
        # box format: [x1, y1, x2, y2]
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
            detected_boxes (list): List of new bounding boxes from the detector.
                                   Format: [x1, y1, x2, y2, conf, cls]

        Returns:
            list: A list of (person_id, box) for all tracked people.
        """
        current_tracked = {}

        # 1. Try to match new detections with existing tracked people
        for person_id, old_box in self.tracked_people.items():
            for i, new_box in enumerate(detected_boxes):
                iou = self._calculate_iou(old_box[:4], new_box[:4])

                if iou > self.iou_threshold:
                    # Match found, update the tracked person's box and add to current_tracked
                    current_tracked[person_id] = new_box
                    # Remove the new box from the list to prevent re-matching
                    detected_boxes.pop(i)
                    break

        # 2. Add any remaining new detections as new people
        for new_box in detected_boxes:
            person_id = self.next_id
            self.tracked_people[person_id] = new_box
            current_tracked[person_id] = new_box
            self.next_id += 1

        # 3. Clean up the tracked_people dictionary to only contain current detections
        self.tracked_people = current_tracked

        return [(person_id, box) for person_id, box in self.tracked_people.items()]
