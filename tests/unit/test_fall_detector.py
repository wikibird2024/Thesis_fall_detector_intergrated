"""FallDetector: decides per person, frame by frame, whether a fall is confirmed."""

import pytest

from builders import lying, standing
from fall_detector.fall.fall_detector import FallDetector


def run_frames(detector: FallDetector, frames: list) -> list[bool]:
    return [detector.detect_fall(landmarks) for landmarks in frames]


def test_no_landmarks_is_not_a_fall():
    assert not FallDetector().detect_fall([])


def test_too_few_landmarks_is_not_a_fall():
    assert not FallDetector().detect_fall(standing()[:20])


def test_low_visibility_key_points_never_confirm_a_fall():
    detector = FallDetector()
    results = run_frames(detector, [lying(visibility=0.1)] * 10)
    assert not any(results)


def test_person_standing_still_is_not_a_fall():
    detector = FallDetector()
    assert not any(run_frames(detector, [standing()] * 20))


@pytest.mark.xfail(strict=True, reason="bug A: confidence check reads z (depth) instead of visibility")
def test_lying_person_is_confirmed_as_fall_after_state_duration():
    detector = FallDetector()
    results = run_frames(detector, [lying()] * 5)
    assert results[-1] is True


@pytest.mark.xfail(strict=True, reason="bug B: upright torso gives angle 180 and counts as lying")
def test_standing_still_with_high_depth_value_is_not_a_fall():
    # depth=0.9 makes the (buggy) confidence check pass, exposing the angle bug.
    detector = FallDetector()
    assert not any(run_frames(detector, [standing(depth=0.9)] * 20))


@pytest.mark.xfail(strict=True, reason="`value or default` replaces an explicit 0 with the default")
def test_explicit_zero_threshold_is_kept():
    detector = FallDetector(velocity_threshold=0.0)
    assert detector.VELOCITY_THRESHOLD == 0.0
