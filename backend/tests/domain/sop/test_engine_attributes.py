from datetime import timedelta
from typing import Any

from app.application.state_codec import matched_from_json, matched_to_json
from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import MatchedEvent, StepStatus
from tests.domain.sop.conftest import (
    T0,
    event_rule,
    make_event,
    make_graph,
    step_spec,
)


def _graph(attributes: dict[str, dict[str, Any]]) -> Any:
    completion = event_rule("batteries_installed", attributes=attributes)
    return make_graph([step_spec("insert", completion=completion)])


def _apply(graph: Any, attributes: dict[str, Any], **overrides: Any) -> Any:
    event = make_event("batteries_installed", attributes=attributes, **overrides)
    return apply(graph, initial_state(graph, "e", T0), event, T0)


def test_count_predicate_requires_two_batteries() -> None:
    graph = _graph({"count": {"gte": 2}})
    one = _apply(graph, {"compartment": "remote", "count": 1, "slots": 2})
    assert all(
        transition.to_status is not StepStatus.COMPLETED
        for transition in one.step_transitions
    )

    two = _apply(graph, {"compartment": "remote", "count": 2, "slots": 2}, event_id="e-2")
    assert two.step_transitions[0].to_status is StepStatus.COMPLETED


def test_eq_predicate_requires_the_exact_value() -> None:
    graph = _graph({"count": {"eq": 2}})
    wrong = _apply(graph, {"compartment": "remote", "count": 1, "slots": 2})
    assert all(
        transition.to_status is not StepStatus.COMPLETED
        for transition in wrong.step_transitions
    )
    right = _apply(graph, {"compartment": "remote", "count": 2, "slots": 2}, event_id="e-2")
    assert right.step_transitions[0].to_status is StepStatus.COMPLETED


def test_in_predicate_checks_membership() -> None:
    graph = _graph({"count": {"in": [2, 3]}})
    rejected = _apply(graph, {"compartment": "remote", "count": 1, "slots": 2})
    assert all(
        transition.to_status is not StepStatus.COMPLETED
        for transition in rejected.step_transitions
    )
    accepted = _apply(graph, {"compartment": "remote", "count": 2, "slots": 2}, event_id="e-2")
    assert accepted.step_transitions[0].to_status is StepStatus.COMPLETED


def test_exists_predicate_can_require_a_missing_attribute() -> None:
    graph = _graph({"count": {"exists": False}})
    present = _apply(graph, {"compartment": "remote", "count": 2, "slots": 2})
    assert all(
        transition.to_status is not StepStatus.COMPLETED
        for transition in present.step_transitions
    )
    absent = _apply(graph, {"compartment": "remote", "slots": 2}, event_id="e-2")
    assert absent.step_transitions[0].to_status is StepStatus.COMPLETED


def test_stable_window_still_applies_with_attributes() -> None:
    completion = event_rule(
        "batteries_installed",
        stable_for_ms=500,
        attributes={"count": {"gte": 2}},
    )
    graph = make_graph([step_spec("insert", completion=completion)])
    state = initial_state(graph, "e", T0)
    first = make_event(
        "batteries_installed",
        event_id="e-1",
        attributes={"compartment": "remote", "count": 2, "slots": 2},
    )
    after_first = apply(graph, state, first, T0)
    assert all(
        transition.to_status is not StepStatus.COMPLETED
        for transition in after_first.step_transitions
    )


def test_matched_attributes_round_trip_through_the_state_codec() -> None:
    matched = MatchedEvent(
        event_id="e-1",
        event_type="batteries_installed",
        confidence=0.9,
        occurred_at=T0 + timedelta(milliseconds=1),
        camera_id="cam-01",
        attributes={"compartment": "remote", "count": 2, "slots": 2},
    )
    restored = matched_from_json(matched_to_json(matched))
    assert dict(restored.attributes) == {
        "compartment": "remote",
        "count": 2,
        "slots": 2,
    }
