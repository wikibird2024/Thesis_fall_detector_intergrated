"""Smoke tests with the real YOLO and MediaPipe models.

Slow and need the [vision] extra plus the yolov8n.pt weights, so they are
marked `vision` and skipped when the packages are missing. CI runs only the
fast tests:  pytest -m "not vision"
"""

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.vision

pytest.importorskip("ultralytics")
pytest.importorskip("mediapipe")

WEIGHTS = Path(__file__).resolve().parents[2] / "yolov8n.pt"


@pytest.fixture(scope="module")
def analyzer():
    if not WEIGHTS.exists():
        pytest.skip(f"model weights not found at {WEIGHTS}")
    from fall_detector.vision.analyzer import PoseFrameAnalyzer
    from fall_detector.vision.human_detector import HumanDetector
    from fall_detector.vision.person_tracker import PersonTracker
    from fall_detector.vision.skeleton_tracker import SkeletonTracker

    analyzer = PoseFrameAnalyzer(HumanDetector(str(WEIGHTS)), PersonTracker(), SkeletonTracker())
    yield analyzer
    analyzer.close()


def test_empty_frame_has_no_people(analyzer):
    assert analyzer.analyze(np.zeros((480, 640, 3), dtype=np.uint8)) == []


def test_skeleton_on_blank_crop_returns_no_landmarks(analyzer):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert analyzer.skeleton.track_from_box(frame, [100, 100, 200, 300, 0.9, 0]) == []


def test_invalid_box_returns_no_landmarks(analyzer):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert analyzer.skeleton.track_from_box(frame, [200, 200, 100, 100, 0.9, 0]) == []
