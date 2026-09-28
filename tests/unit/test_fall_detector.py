"""FallDetector: decides per person, frame by frame, whether a fall is confirmed."""

import pytest

from builders import lying, standing, tilted
from fall_detector.fall.fall_detector import FallDetector, FallThresholds, torso_tilt_deg


def run_frames(detector: FallDetector, frames: list) -> list[bool]:
    return [detector.detect_fall(landmarks) for landmarks in frames]


# ---------------------------------------------------------------- geometry


@pytest.mark.parametrize(
    ("landmarks", "expected_deg"),
    [
        (standing(), 0.0),
        (lying(), 90.0),
        (tilted(45), 45.0),
        (tilted(-45), 45.0),  # leaning left or right is the same tilt
        (tilted(180), 180.0),  # upside down
    ],
    ids=["standing", "lying", "lean-right", "lean-left", "upside-down"],
)
def test_torso_tilt(landmarks, expected_deg):
    assert torso_tilt_deg(landmarks) == pytest.approx(expected_deg, abs=0.01)


# ---------------------------------------------------------------- invalid input


def test_no_landmarks_is_not_a_fall():
    assert not FallDetector().detect_fall([])


def test_too_few_landmarks_is_not_a_fall():
    assert not FallDetector().detect_fall(standing()[:20])


def test_low_visibility_key_points_never_confirm_a_fall():
    detector = FallDetector()
    assert not any(run_frames(detector, [lying(visibility=0.1)] * 10))


def test_depth_value_does_not_affect_reliability():
    # Regression (bug A): z (depth) used to be read as confidence.
    detector = FallDetector()
    assert detector.has_reliable_key_points(lying(depth=-0.8))
    assert not detector.has_reliable_key_points(lying(depth=0.9, visibility=0.1))


# ---------------------------------------------------------------- decisions


@pytest.mark.parametrize("depth", [-0.3, 0.0, 0.9])
def test_person_standing_still_is_not_a_fall(depth):
    # Regression (bug B): upright torso used to measure 180 deg and count as lying.
    detector = FallDetector()
    assert not any(run_frames(detector, [standing(depth=depth)] * 20))


def test_slight_lean_is_not_a_fall():
    detector = FallDetector()
    assert not any(run_frames(detector, [tilted(30)] * 20))


def test_lying_person_is_confirmed_on_the_fifth_frame():
    detector = FallDetector()
    assert run_frames(detector, [lying()] * 5) == [False, False, False, False, True]


def test_fast_fall_is_confirmed_by_motion():
    # Tilted past 60 deg (not enough to count as lying) while moving 10 px per frame.
    detector = FallDetector(FallThresholds(falling_frames=3))
    frames = [tilted(65, hip=(300 + 10 * i, 300)) for i in range(4)]
    # Frame 1 has no previous position, so speed is 0; frames 2-4 are moving.
    assert run_frames(detector, frames) == [False, False, False, True]


def test_getting_up_resets_the_count():
    detector = FallDetector()
    frames = [lying()] * 4 + [standing()] + [lying()] * 4
    assert not any(run_frames(detector, frames))


def test_fall_fires_once_then_counting_starts_again():
    detector = FallDetector()
    results = run_frames(detector, [lying()] * 10)
    assert results.count(True) == 2  # frame 5 and frame 10


def test_explicit_zero_threshold_is_kept():
    # Regression: `value or default` used to replace 0 with the default.
    thresholds = FallThresholds(velocity_threshold_px=0.0)
    assert FallDetector(thresholds).thresholds.velocity_threshold_px == 0.0
