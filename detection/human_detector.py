# human_detector.py
import cv2
import numpy as np
from ultralytics import YOLO


class HumanDetector:
    def __init__(self, model_path="yolov8n.pt", conf_threshold=0.5, iou_threshold=0.7):
        """
        Initializes the human detector with a YOLO model.
        Args:
            model_path (str): Path to the YOLO model weights.
        """
        self.model = YOLO(model_path)
        self.class_id_person = 0
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

    def detect_humans(self, frame):
        """
        Detects humans in a video frame.
        Args:
            frame: The input video frame (numpy array).
        Returns:
            A list of detected person bounding boxes.
        """
        results = self.model.predict(
            frame, conf=self.conf_threshold, iou=self.iou_threshold, verbose=False
        )[0]

        if results.boxes is None or results.boxes.xyxy is None:
            return []

        boxes = results.boxes.xyxy.cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()
        clss = results.boxes.cls.cpu().numpy().astype(int)

        person_boxes = []
        for box, conf, cls in zip(boxes, confs, clss):
            if cls == self.class_id_person:
                x1, y1, x2, y2 = map(int, box)
                person_boxes.append([x1, y1, x2, y2, float(conf), cls])

        return person_boxes
