"""PersonTracker: gives each detected person a stable id across frames."""

from builders import box
from fall_detector.vision.person_tracker import PersonTracker


def ids(tracked: list) -> list[int]:
    return [person_id for person_id, _ in tracked]


def test_new_detections_get_new_ids_in_order():
    tracker = PersonTracker(iou_threshold=0.3)
    tracked = tracker.update([box(0, 0, 100, 200), box(300, 0, 400, 200)])
    assert ids(tracked) == [0, 1]


def test_same_person_keeps_id_when_box_moves_slightly():
    tracker = PersonTracker(iou_threshold=0.3)
    tracker.update([box(0, 0, 100, 200)])
    tracked = tracker.update([box(5, 5, 105, 205)])
    assert ids(tracked) == [0]


def test_track_matches_best_overlap_not_first_overlap():
    tracker = PersonTracker(iou_threshold=0.3)
    tracker.update([box(0, 0, 100, 200)])
    # Both new boxes overlap the track; the second one overlaps much more.
    tracked = dict(tracker.update([box(40, 0, 140, 200), box(2, 0, 102, 200)]))
    assert tracked[0][:4] == [2, 0, 102, 200]
    assert tracked[1][:4] == [40, 0, 140, 200]


def test_person_who_leaves_is_dropped_and_returning_person_gets_new_id():
    tracker = PersonTracker(iou_threshold=0.3)
    tracker.update([box(0, 0, 100, 200)])
    assert tracker.update([]) == []
    assert ids(tracker.update([box(0, 0, 100, 200)])) == [1]


def test_no_overlap_means_new_person():
    tracker = PersonTracker(iou_threshold=0.3)
    tracker.update([box(0, 0, 100, 200)])
    assert ids(tracker.update([box(500, 0, 600, 200)])) == [1]
