
import cv2
import numpy as np
import mediapipe as mp
from config.config import (
    BOUNDING_BOX_COLOR,
    BOUNDING_BOX_THICKNESS,
    SKELETON_LINE_COLOR,
    SKELETON_LINE_THICKNESS,
    SKELETON_POINT_COLOR,
    SKELETON_POINT_RADIUS
)

mp_pose = mp.solutions.pose
POSE_CONNECTIONS = mp_pose.POSE_CONNECTIONS


def draw_bounding_box(frame, box, person_id, status,
                      color=BOUNDING_BOX_COLOR, thickness=BOUNDING_BOX_THICKNESS):
    """
    Draws a bounding box with an ID and status label, changing color based on status.
    """
    x1, y1, x2, y2, conf, cls_id = box

    # Choose color based on status
    if status == 'fall':
        box_color = (0, 0, 255)  # Red for fall
    else:
        box_color = (0, 255, 0)  # Green for normal/default

    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness)

    # Display the person ID, status, and confidence
    label = f"ID: {person_id} | Status: {status} | Conf: {conf:.2f}"
    cv2.putText(
        frame,
        label,
        (x1, y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        box_color,
        2,
    )


def draw_skeleton(frame, landmarks, visibility_th=0.5,
                  line_color=SKELETON_LINE_COLOR, line_thickness=SKELETON_LINE_THICKNESS,
                  point_color=SKELETON_POINT_COLOR, point_radius=SKELETON_POINT_RADIUS):
    """
    Draws a person's skeleton based on a list of landmarks in the format [x, y, z, visibility].
    """
    if not landmarks:
        return

    for start_idx, end_idx in POSE_CONNECTIONS:
        if start_idx < len(landmarks) and end_idx < len(landmarks):
            start = landmarks[start_idx]
            end = landmarks[end_idx]

            if start[3] > visibility_th and end[3] > visibility_th:
                x1, y1 = int(start[0]), int(start[1])
                x2, y2 = int(end[0]), int(end[1])
                cv2.line(frame, (x1, y1), (x2, y2), line_color, line_thickness)

    for lm in landmarks:
        if lm[3] > visibility_th:
            cx, cy = int(lm[0]), int(lm[1])
            cv2.circle(frame, (cx, cy), point_radius, point_color, -1)


def draw_person(frame, box, landmarks, person_id: str, status: str):
    """
    High-level function: draws both bounding box and skeleton for one person.
    """
    draw_bounding_box(frame, box, person_id, status)
    draw_skeleton(frame, landmarks)
