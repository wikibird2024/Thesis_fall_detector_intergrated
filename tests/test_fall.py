"""
Unit test for FallDetector.
"""

from fall.fall_detector import FallDetector

def test_no_fall():
    detector = FallDetector()
    assert detector.is_fall([]) == False
