from dataclasses import replace
from datetime import timedelta

import pytest
from conftest import T, make_detection, make_frame, make_perception
from pydantic import ValidationError

from video_runtime.config import BindingConfig
from video_runtime.event_builder import EventBuilder, binding_from_config
from video_runtime.evidence import EvidenceWriter


def make_binding(
    event_type: str = "bottle_in_pickup_zone",
    *,
    zone: str = "pickup",
    rect: tuple[float, float, float, float] = (0.0, 0.0, 0.5, 1.0),
    emit_interval_ms: int = 500,
):
    return binding_from_config(
        BindingConfig(
            event_type=event_type,
            primitive="object_in_zone",
            params={
                "object_class": "bottle",
                "zone": zone,
                "rect": rect,
                "min_conf": 0.25,
            },
            emit_interval_ms=emit_interval_ms,
        )
    )


def make_builder(tmp_path, bindings=None) -> EventBuilder:
    return EventBuilder(
        "st-01",
        "cam-01",
        "overview",
        "yolo11n-coco",
        "1",
        EvidenceWriter(tmp_path),
        bindings=bindings or [make_binding()],
    )


def test_emits_one_event_per_binding_per_interval(tmp_path) -> None:
    frame = make_frame(seq=1, at=T)
    perception = make_perception((make_detection(),), frame=frame)
    builder = make_builder(tmp_path)

    first = builder.build(frame, perception, now=T)
    second_perception = replace(
        perception,
        frame=replace(frame, frame_seq=2, captured_at=T + timedelta(milliseconds=100)),
    )
    second = builder.build(
        second_perception.frame, second_perception, now=T + timedelta(milliseconds=100)
    )
    third_perception = replace(
        perception,
        frame=replace(frame, frame_seq=3, captured_at=T + timedelta(milliseconds=600)),
    )
    third = builder.build(
        third_perception.frame, third_perception, now=T + timedelta(milliseconds=600)
    )

    assert len(first) == 1 and second == [] and len(third) == 1
    event = first[0]
    assert event.event_type == "bottle_in_pickup_zone"
    assert event.primitive_id == "object_in_zone"
    assert event.primitive_version == "1.0"
    assert event.binding_id.startswith("bottle_in_pickup_zone:")
    assert event.params_hash
    assert len(event.observation_ids) == 1
    assert event.correlation_key == "st-01:pickup:bottle"
    assert event.attributes["zone"] == "pickup"
    assert (tmp_path / event.evidence_refs[0]).exists()


def test_two_bindings_get_two_events_with_their_own_evidence(tmp_path) -> None:
    builder = make_builder(
        tmp_path,
        bindings=[
            make_binding(),
            make_binding(
                "bottle_in_target_zone",
                zone="target",
                rect=(0.5, 0.0, 1.0, 1.0),
            ),
        ],
    )
    perception = make_perception(
        (
            make_detection("bottle", 0.9, (0.1, 0.1, 0.3, 0.3)),
            make_detection("bottle", 0.8, (0.6, 0.6, 0.8, 0.8)),
        )
    )
    events = builder.build(make_frame(seq=1, at=T), perception, now=T)
    assert [event.event_type for event in events] == [
        "bottle_in_pickup_zone",
        "bottle_in_target_zone",
    ]
    assert len({event.event_id for event in events}) == 2
    assert len({event.evidence_refs[0] for event in events}) == 2
    assert events[1].correlation_key == "st-01:target:bottle"


def test_an_unregistered_event_type_is_rejected_at_binding_time() -> None:
    with pytest.raises(ValidationError, match="not_registered"):
        binding_from_config(
            BindingConfig(
                event_type="not_registered",
                primitive="object_in_zone",
                params={
                    "object_class": "bottle",
                    "zone": "pickup",
                    "rect": (0.0, 0.0, 0.5, 1.0),
                },
            )
        )


class FailingWriter(EvidenceWriter):
    def write(self, event_id, frame, **kwargs) -> str:
        raise OSError("disk full")


def test_evidence_write_failure_still_emits_the_event(tmp_path) -> None:
    builder = EventBuilder(
        "st-01",
        "cam-01",
        "overview",
        "yolo11n-coco",
        "1",
        FailingWriter(tmp_path),
        bindings=[make_binding()],
    )
    events = builder.build(
        make_frame(seq=1, at=T),
        make_perception((make_detection(),)),
        now=T,
    )
    assert len(events) == 1
    assert events[0].evidence_refs == ()
