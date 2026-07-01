
import math
from typing import List, Tuple, Optional
from config import config  # Import thresholds and configuration values

class FallDetector:
    """
    Fall detector improved to detect falls in all directions, 
    including sideways and forward/backward.
    """
    def __init__(
        self,
        torso_angle_threshold_vertical: float = None,
        torso_angle_threshold_horizontal: float = None,
        velocity_threshold: float = None,
        fall_duration_threshold: int = None,
        fall_state_duration_threshold: int = None,
        min_landmark_confidence: float = None
    ):
        # Thresholds and configuration parameters
        self.TORSO_ANGLE_THRESHOLD_VERTICAL = torso_angle_threshold_vertical or config.TORSO_ANGLE_THRESHOLD_VERTICAL
        self.TORSO_ANGLE_THRESHOLD_HORIZONTAL = torso_angle_threshold_horizontal or config.TORSO_ANGLE_THRESHOLD_HORIZONTAL
        self.VELOCITY_THRESHOLD = velocity_threshold or config.VELOCITY_THRESHOLD
        self.FALL_DURATION_THRESHOLD = fall_duration_threshold or config.FALL_DURATION_THRESHOLD
        self.FALL_STATE_DURATION_THRESHOLD = fall_state_duration_threshold or config.FALL_STATE_DURATION_THRESHOLD
        self.MIN_LANDMARK_CONFIDENCE = min_landmark_confidence or config.MIN_LANDMARK_CONFIDENCE

        # Internal state counters to track consecutive fall frames
        self.consecutive_frames_fallen = 0
        self.frames_in_fall_state = 0

        # Store previous torso center to calculate velocity between frames
        self.previous_torso_center: Optional[Tuple[float,float]] = None

        # Indices of key landmarks (based on standard pose detection model)
        self.LEFT_SHOULDER = 11
        self.RIGHT_SHOULDER = 12
        self.LEFT_HIP = 23
        self.RIGHT_HIP = 24

    def reset(self):
        """Reset internal state after a fall is detected or landmarks are invalid."""
        self.consecutive_frames_fallen = 0
        self.frames_in_fall_state = 0
        self.previous_torso_center = None

    def _calculate_torso_angle(self, landmarks: List[Tuple[float, float]]) -> Tuple[float, float]:
        """
        Calculate torso angles relative to vertical and horizontal axes.

        Args:
            landmarks: List of (x, y) coordinates for each body keypoint.

        Returns:
            angle_vertical: angle between torso and vertical axis (degrees)
            angle_horizontal: angle between torso and horizontal axis (degrees)
        """
        left_shoulder = landmarks[self.LEFT_SHOULDER]
        right_shoulder = landmarks[self.RIGHT_SHOULDER]
        left_hip = landmarks[self.LEFT_HIP]
        right_hip = landmarks[self.RIGHT_HIP]

        # Midpoints of shoulders and hips to define the torso line
        torso_top = ((left_shoulder[0] + right_shoulder[0]) / 2,
                     (left_shoulder[1] + right_shoulder[1]) / 2)
        torso_bottom = ((left_hip[0] + right_hip[0]) / 2,
                        (left_hip[1] + right_hip[1]) / 2)

        dx = torso_top[0] - torso_bottom[0]  # Horizontal component
        dy = torso_top[1] - torso_bottom[1]  # Vertical component

        # Angle calculation using arctangent
        angle_vertical = abs(math.degrees(math.atan2(dx, dy)))      # Deviation from vertical
        angle_horizontal = abs(math.degrees(math.atan2(dy, dx)))    # Deviation from horizontal

        return angle_vertical, angle_horizontal

    def _calculate_velocity(self, landmarks: List[Tuple[float, float]]) -> float:
        """
        Calculate torso velocity based on movement between consecutive frames.

        Args:
            landmarks: List of (x, y) coordinates for each body keypoint.

        Returns:
            velocity magnitude in pixels per frame
        """
        left_shoulder = landmarks[self.LEFT_SHOULDER]
        right_shoulder = landmarks[self.RIGHT_SHOULDER]
        left_hip = landmarks[self.LEFT_HIP]
        right_hip = landmarks[self.RIGHT_HIP]

        # Torso center as average of shoulder and hip keypoints
        torso_center = (
            (left_shoulder[0] + right_shoulder[0] + left_hip[0] + right_hip[0]) / 4,
            (left_shoulder[1] + right_shoulder[1] + left_hip[1] + right_hip[1]) / 4,
        )

        # First frame: cannot compute velocity
        if self.previous_torso_center is None:
            self.previous_torso_center = torso_center
            return 0.0

        # Velocity vector = difference between current and previous torso center
        vx = torso_center[0] - self.previous_torso_center[0]
        vy = torso_center[1] - self.previous_torso_center[1]
        velocity_mag = math.sqrt(vx**2 + vy**2)  # Euclidean distance

        self.previous_torso_center = torso_center  # Update previous torso position
        return velocity_mag

    def detect_fall(self, landmarks: List[Tuple[float, float]]) -> bool:
        """
        Detect a fall based on torso angles and velocity.

        Args:
            landmarks: List of (x, y, confidence) for each keypoint.

        Returns:
            True if a fall is detected, False otherwise.
        """
        # Validate landmarks length (expecting at least 33 keypoints)
        if not landmarks or len(landmarks) < 33:
            self.reset()
            return False

        # Check confidence of critical landmarks
        for idx in [self.LEFT_SHOULDER, self.RIGHT_SHOULDER, self.LEFT_HIP, self.RIGHT_HIP]:
            if len(landmarks[idx]) < 3 or landmarks[idx][2] < self.MIN_LANDMARK_CONFIDENCE:
                # Reset if key landmarks are not reliable
                self.reset()
                return False

        # Extract (x, y) coordinates only, discard confidence
        coords = [(lm[0], lm[1]) for lm in landmarks]

        # Compute torso angles and velocity
        angle_v, angle_h = self._calculate_torso_angle(coords)
        velocity = self._calculate_velocity(coords)

        # Determine if subject is actively falling
        is_falling = (
            (angle_v > self.TORSO_ANGLE_THRESHOLD_VERTICAL or angle_h > self.TORSO_ANGLE_THRESHOLD_HORIZONTAL)
            and velocity > self.VELOCITY_THRESHOLD
        )

        # Determine if subject is lying on the ground
        is_lying = (
            angle_v > self.TORSO_ANGLE_THRESHOLD_VERTICAL + 10 or
            angle_h > self.TORSO_ANGLE_THRESHOLD_HORIZONTAL + 10
        )

        # Update internal counters based on current state
        if is_falling:
            self.consecutive_frames_fallen += 1
            self.frames_in_fall_state = 0
        elif is_lying:
            self.consecutive_frames_fallen = 0
            self.frames_in_fall_state += 1
        else:
            self.consecutive_frames_fallen = 0
            self.frames_in_fall_state = 0

        # Check thresholds to confirm fall
        is_fall_detected = (
            self.consecutive_frames_fallen >= self.FALL_DURATION_THRESHOLD or
            self.frames_in_fall_state >= self.FALL_STATE_DURATION_THRESHOLD
        )

        if is_fall_detected:
            # Reset after confirming fall to avoid repeated detection
            self.reset()

        return is_fall_detected
