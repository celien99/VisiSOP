from datetime import timedelta

from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import StepStatus
from tests.domain.sop.conftest import T0, make_event


def test_any_rule_completes_on_one_of_two_events(any_graph) -> None:
    result = apply(
        any_graph,
        initial_state(any_graph, "e", T0),
        make_event("b_done"),
        T0 + timedelta(seconds=1),
    )
    assert result.step_transitions[0].to_status is StepStatus.COMPLETED


def test_not_rule_blocks_completion(not_graph) -> None:
    state = initial_state(not_graph, "e", T0)
    blocked = apply(not_graph, state, make_event("part_removed"), T0)
    assert all(
        t.to_status is not StepStatus.COMPLETED
        for t in blocked.step_transitions
    )


def test_stable_for_ms_needs_a_span(stable_graph, state_with_first_event) -> None:
    early = apply(
        stable_graph,
        state_with_first_event,
        make_event(
            "present",
            event_id="e-2",
            occurred_at=T0 + timedelta(milliseconds=100),
        ),
        T0 + timedelta(milliseconds=100),
    )
    assert all(
        t.to_status is not StepStatus.COMPLETED for t in early.step_transitions
    )
    late = apply(
        stable_graph,
        state_with_first_event,
        make_event(
            "present",
            event_id="e-2",
            occurred_at=T0 + timedelta(milliseconds=600),
        ),
        T0 + timedelta(milliseconds=600),
    )
    assert late.step_transitions[0].to_status is StepStatus.COMPLETED


def test_within_ms_rejects_late_evidence(within_graph) -> None:
    result = apply(
        within_graph,
        initial_state(within_graph, "e", T0),
        make_event("present", occurred_at=T0 + timedelta(milliseconds=600)),
        T0 + timedelta(milliseconds=600),
    )
    assert all(
        t.to_status is not StepStatus.COMPLETED for t in result.step_transitions
    )


def test_source_camera_role_is_enforced(role_graph) -> None:
    wrong = apply(
        role_graph,
        initial_state(role_graph, "e", T0),
        make_event("present", camera_role="hands"),
        T0,
    )
    assert all(
        t.to_status is not StepStatus.COMPLETED for t in wrong.step_transitions
    )
    right = apply(
        role_graph,
        initial_state(role_graph, "e", T0),
        make_event("present", camera_role="overview"),
        T0,
    )
    assert right.step_transitions[0].to_status is StepStatus.COMPLETED
