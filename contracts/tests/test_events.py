from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.events import ModelRef, Observation, RoutedSOPEvent, VisionEvent

T = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_event(**overrides: Any) -> VisionEvent:
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "event_id": "e-1",
        "event_type": "part_placed",
        "station_id": "station-01",
        "camera_id": "camera-left",
        "camera_role": "hands",
        "occurred_at": T,
        "emitted_at": T,
        "frame_seq": 1,
        "confidence": 0.9,
        "model": ModelRef(name="detector", version="1"),
        "attributes": {"part_id": "p1"},
    }
    return VisionEvent(**{**data, **overrides})


def test_valid_event_round_trips_to_json() -> None:
    event = make_event()
    assert VisionEvent.model_validate_json(event.model_dump_json()) == event


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(occurred_at=datetime(2026, 1, 1, 12, 0))  # noqa: DTZ001


def test_confidence_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(confidence=1.5)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(extra_field=True)


def test_routed_event_requires_execution_id() -> None:
    with pytest.raises(ValidationError):
        RoutedSOPEvent(**make_event().model_dump())


def _routed_payload(**overrides: Any) -> dict[str, Any]:
    payload = make_event().model_dump()
    payload.pop("execution_id")
    return {**payload, **overrides}


def test_routed_event_requires_resolver_rule_version() -> None:
    with pytest.raises(ValidationError):
        RoutedSOPEvent(
            **_routed_payload(),
            execution_id="exec-1",
            resolution_method="ACTIVE_EXECUTION_WINDOW",
            resolved_at=T,
            candidate_ids=("exec-1",),
        )


def test_routed_event_carries_resolution_metadata() -> None:
    routed = RoutedSOPEvent(
        **_routed_payload(),
        execution_id="exec-1",
        resolution_method="ACTIVE_EXECUTION_WINDOW",
        resolved_at=T,
        resolver_rule_version="1",
        candidate_ids=("exec-1",),
    )
    assert routed.execution_id == "exec-1"


def test_observation_allows_empty_execution_id() -> None:
    observation = Observation(
        schema_version="1.0",
        observation_id="o-1",
        station_id="s1",
        camera_id="c1",
        occurred_at=T,
        frame_seq=0,
        confidence=0.9,
        model=ModelRef(name="detector", version="1"),
        attributes={},
        evidence_refs=(),
    )
    assert observation.execution_id is None


def test_optional_fields_are_backward_compatible() -> None:
    payload = make_event().model_dump(mode="json")
    payload.pop("camera_role")
    payload.pop("correlation_key")
    assert VisionEvent.model_validate(payload).camera_role is None


def test_vision_event_accepts_optional_execution_hint() -> None:
    assert make_event().execution_id is None
    assert make_event(execution_id="exec-1").execution_id == "exec-1"


def test_routed_event_still_requires_execution_id() -> None:
    with pytest.raises(ValidationError):
        RoutedSOPEvent(
            **make_event().model_dump(),
            resolution_method="ACTIVE_EXECUTION_WINDOW",
            resolved_at=T,
            resolver_rule_version="1",
        )
