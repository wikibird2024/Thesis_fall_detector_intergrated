"""
Unit test for FallDetector.
"""

from fall_detector.fall.fall_detector import FallDetector


def test_no_fall():
    detector = FallDetector()
    assert detector.detect_fall([]) == False
