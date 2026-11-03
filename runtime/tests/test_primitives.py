import pytest
from conftest import make_detection, make_perception
from contracts.primitives import (
    CountThresholdParams,
    ObjectAbsentParams,
    ObjectInZoneParams,
    ObjectPresentParams,
    OrientationMatchParams,
    StateClassifyParams,
)

from video_runtime.primitives import build_primitive
from video_runtime.primitives.count import CountThreshold
from video_runtime.primitives.in_zone import ObjectInZone
from video_runtime.primitives.orientation import OrientationMatch
from video_runtime.primitives.presence import ObjectAbsent, ObjectPresent
from video_runtime.primitives.state import StateClassify


def test_object_in_zone_returns_the_highest_confidence_hit() -> None:
    params = ObjectInZoneParams(
        object_class="bottle", zone="pickup", rect=(0.0, 0.0, 0.5, 1.0)
    )
    perception = make_perception(
        (
            make_detection("bottle", 0.7, (0.1, 0.1, 0.2, 0.2)),
            make_detection("bottle", 0.9, (0.3, 0.3, 0.4, 0.4)),
            make_detection("bottle", 0.95, (0.7, 0.7, 0.9, 0.9)),
        )
    )
    [observation] = ObjectInZone().evaluate(perception, params)
    assert observation.attributes["zone"] == "pickup"
    assert observation.attributes["bbox"] == (0.3, 0.3, 0.4, 0.4)
    assert observation.confidence == 0.9
    assert observation.regions == ((0.0, 0.0, 0.5, 1.0),)


def test_object_present_accepts_a_missing_rect() -> None:
    params = ObjectPresentParams(object_class="remote", zone="bench")
    perception = make_perception((make_detection("remote", 0.8, (0.5, 0.5, 0.6, 0.6)),))
    [observation] = ObjectPresent().evaluate(perception, params)
    assert observation.attributes["zone"] == "bench"
    assert observation.regions == ()


def test_object_absent_needs_the_debounce_frames() -> None:
    params = ObjectAbsentParams(object_class="hand", zone="bench", frames=3)
    primitive = ObjectAbsent()
    empty = make_perception(())
    assert primitive.evaluate(empty, params) == []
    assert primitive.evaluate(empty, params) == []
    [absent] = primitive.evaluate(empty, params)
    assert absent.attributes == {"zone": "bench", "present": False}
    assert absent.confidence == 1.0

    [present] = primitive.evaluate(
        make_perception((make_detection("hand", 0.8, (0.1, 0.1, 0.2, 0.2)),)), params
    )
    assert present.attributes["present"] is True


def test_count_threshold_counts_only_instances_in_the_roi() -> None:
    params = CountThresholdParams(
        object_class="battery", compartment="remote", roi=(0.0, 0.0, 0.5, 1.0)
    )
    perception = make_perception(
        (
            make_detection("battery", 0.9, (0.1, 0.1, 0.2, 0.2)),
            make_detection("battery", 0.8, (0.3, 0.3, 0.4, 0.4)),
            make_detection("battery", 0.99, (0.7, 0.7, 0.9, 0.9)),
        )
    )
    [observation] = CountThreshold().evaluate(perception, params)
    assert observation.attributes == {
        "compartment": "remote",
        "count": 2,
        "slots": 2,
    }
    assert observation.confidence == pytest.approx(0.85)
    assert len(observation.boxes) == 2


def test_count_threshold_includes_orientation_classes() -> None:
    params = CountThresholdParams(
        object_class="battery",
        count_classes=("CORRECT", "REVERSED"),
        compartment="remote",
        roi=(0.0, 0.0, 1.0, 1.0),
    )
    perception = make_perception(
        (
            make_detection("battery", 0.9, (0.1, 0.1, 0.2, 0.2)),
            make_detection("CORRECT", 0.8, (0.3, 0.3, 0.4, 0.4)),
            make_detection("REVERSED", 0.7, (0.5, 0.5, 0.6, 0.6)),
            make_detection("hand", 0.99, (0.7, 0.7, 0.8, 0.8)),
        )
    )
    [observation] = CountThreshold().evaluate(perception, params)
    assert observation.attributes["count"] == 3
    assert observation.confidence == pytest.approx(0.8)


def test_count_threshold_dedupes_overlapping_boxes() -> None:
    params = CountThresholdParams(
        object_class="battery",
        count_classes=("CORRECT",),
        compartment="remote",
        roi=(0.0, 0.0, 1.0, 1.0),
    )
    perception = make_perception(
        (
            make_detection("battery", 0.9, (0.1, 0.1, 0.2, 0.2)),
            make_detection("CORRECT", 0.6, (0.1, 0.1, 0.2, 0.2)),
        )
    )
    [observation] = CountThreshold().evaluate(perception, params)
    assert observation.attributes["count"] == 1
    assert observation.confidence == pytest.approx(0.9)


def test_count_threshold_reports_zero_without_hits() -> None:
    params = CountThresholdParams(
        object_class="battery",
        compartment="remote",
        roi=(0.0, 0.0, 0.5, 0.5),
    )
    [observation] = CountThreshold().evaluate(make_perception(()), params)
    assert observation.attributes["count"] == 0
    assert observation.confidence == 0.0


def test_state_classify_picks_the_state_label() -> None:
    params = StateClassifyParams(roi=(0.0, 0.0, 0.5, 1.0), states=("OPEN", "CLOSED"))
    perception = make_perception(
        (
            make_detection("OPEN", 0.6, (0.1, 0.1, 0.2, 0.2)),
            make_detection("CLOSED", 0.9, (0.2, 0.2, 0.3, 0.3)),
        )
    )
    [observation] = StateClassify().evaluate(perception, params)
    assert observation.attributes == {"state": "CLOSED"}


def test_state_classify_ignores_states_outside_the_roi() -> None:
    params = StateClassifyParams(roi=(0.0, 0.0, 0.5, 1.0), states=("OPEN", "CLOSED"))
    perception = make_perception((make_detection("CLOSED", 0.9, (0.7, 0.7, 0.9, 0.9)),))
    assert StateClassify().evaluate(perception, params) == []


def test_orientation_match_maps_the_class_to_an_orientation() -> None:
    params = OrientationMatchParams(
        object_class="battery",
        compartment="remote",
        roi=(0.0, 0.0, 0.5, 1.0),
    )
    perception = make_perception(
        (make_detection("CORRECT", 0.9, (0.2, 0.2, 0.3, 0.3)),)
    )
    [observation] = OrientationMatch().evaluate(perception, params)
    assert observation.attributes == {
        "compartment": "remote",
        "orientation": "CORRECT",
    }


def test_unimplemented_primitives_fail_loudly() -> None:
    with pytest.raises(NotImplementedError, match="no runtime implementation"):
        build_primitive("object_placed")
