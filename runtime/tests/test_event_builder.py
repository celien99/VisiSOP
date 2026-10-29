from dataclasses import replace
from datetime import timedelta

from conftest import T, make_detection, make_frame

from video_runtime.event_builder import EventBuilder
from video_runtime.evidence import EvidenceWriter
from video_runtime.zones import Zone, ZoneHit

PICKUP = Zone(
    "pickup",
    (0.0, 0.0, 0.5, 1.0),
    frozenset({"bottle"}),
    "bottle_in_pickup_zone",
    0.25,
    500,
)
TARGET = Zone(
    "target",
    (0.5, 0.0, 1.0, 1.0),
    frozenset({"bottle"}),
    "bottle_in_target_zone",
    0.25,
    500,
)


def make_builder(tmp_path) -> EventBuilder:
    return EventBuilder(
        "st-01", "cam-01", "overview", "yolo11n-coco", "1", EvidenceWriter(tmp_path)
    )


def test_emits_one_event_per_zone_per_interval(tmp_path) -> None:
    frame = make_frame(seq=1, at=T)
    hit = ZoneHit(zone=PICKUP, detection=make_detection("bottle", 0.9))
    builder = make_builder(tmp_path)
    first = builder.build(frame, [hit], now=T)
    second = builder.build(
        replace(frame, frame_seq=2, captured_at=T + timedelta(milliseconds=100)),
        [hit],
        now=T + timedelta(milliseconds=100),
    )
    third = builder.build(
        replace(frame, frame_seq=3, captured_at=T + timedelta(milliseconds=600)),
        [hit],
        now=T + timedelta(milliseconds=600),
    )
    assert len(first) == 1 and second == [] and len(third) == 1
    event = first[0]
    assert event.event_type == "bottle_in_pickup_zone"
    assert event.correlation_key == "st-01:pickup:bottle"
    assert event.occurred_at == T
    assert event.emitted_at == T
    assert event.frame_seq == 1
    assert event.confidence == 0.9
    assert event.attributes["zone"] == "pickup"
    assert (tmp_path / event.evidence_refs[0]).exists()


def test_two_zones_get_two_events_with_their_own_evidence(tmp_path) -> None:
    builder = make_builder(tmp_path)
    events = builder.build(
        make_frame(seq=1, at=T),
        [
            ZoneHit(zone=PICKUP, detection=make_detection()),
            ZoneHit(zone=TARGET, detection=make_detection()),
        ],
        now=T,
    )
    assert [event.event_type for event in events] == [
        "bottle_in_pickup_zone",
        "bottle_in_target_zone",
    ]
    assert len({event.event_id for event in events}) == 2
    assert len({event.evidence_refs[0] for event in events}) == 2
    assert events[1].correlation_key == "st-01:target:bottle"
