from datetime import timedelta

from conftest import T, make_detection

from video_runtime.perception import IoUTracker, iou


def test_iou_is_one_for_identical_boxes_and_zero_when_disjoint() -> None:
    box = (0.1, 0.1, 0.3, 0.3)
    assert iou(box, box) == 1.0
    assert iou(box, (0.5, 0.5, 0.7, 0.7)) == 0.0


def test_tracker_keeps_the_id_across_frames() -> None:
    tracker = IoUTracker()
    first = tracker.update(
        (make_detection(bbox=(0.1, 0.1, 0.3, 0.3)),), camera_id="cam-01", at=T
    )
    second = tracker.update(
        (make_detection(bbox=(0.11, 0.1, 0.31, 0.3)),),
        camera_id="cam-01",
        at=T + timedelta(milliseconds=100),
    )
    assert first[0].track_id == second[0].track_id
    assert second[0].hits == 2


def test_a_new_object_gets_a_new_id() -> None:
    tracker = IoUTracker()
    first = tracker.update(
        (make_detection(bbox=(0.1, 0.1, 0.3, 0.3)),), camera_id="cam-01", at=T
    )
    second = tracker.update(
        (make_detection(bbox=(0.6, 0.6, 0.8, 0.8)),), camera_id="cam-01", at=T
    )
    assert first[0].track_id != second[0].track_id


def test_a_track_expires_after_the_missed_frame_budget() -> None:
    tracker = IoUTracker(max_missed=1)
    first = tracker.update(
        (make_detection(bbox=(0.1, 0.1, 0.3, 0.3)),), camera_id="cam-01", at=T
    )
    tracker.update((), camera_id="cam-01", at=T + timedelta(milliseconds=100))
    tracker.update((), camera_id="cam-01", at=T + timedelta(milliseconds=200))
    again = tracker.update(
        (make_detection(bbox=(0.1, 0.1, 0.3, 0.3)),), camera_id="cam-01", at=T
    )
    assert again[0].track_id != first[0].track_id
