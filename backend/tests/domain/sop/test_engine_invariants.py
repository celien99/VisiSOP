import dataclasses

from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import StepStatus
from contracts.enums import ReasonCode
from tests.domain.sop.conftest import T0, make_event


def test_late_event_does_not_roll_back_completed(graph_ab, state_with_a_done) -> None:
    result = apply(
        graph_ab,
        state_with_a_done,
        make_event("a_done", event_id="e-2"),
        T0,
    )
    assert all(
        t.step_key != "a" or t.from_status != StepStatus.COMPLETED
        for t in result.step_transitions
    )


def test_late_event_after_timeout_goes_to_review(
    graph_ab, state_with_a_timed_out
) -> None:
    result = apply(
        graph_ab,
        state_with_a_timed_out,
        make_event("a_done", event_id="e-3"),
        T0,
    )
    transition = next(t for t in result.step_transitions if t.step_key == "a")
    assert transition.to_status is StepStatus.NEEDS_REVIEW
    assert transition.reason_code is ReasonCode.LATE_EVENT


def test_terminal_execution_ignores_events(graph_ab, state_completed) -> None:
    result = apply(graph_ab, state_completed, make_event("a_done"), T0)
    assert result.step_transitions == ()
    assert result.reason_code is ReasonCode.LATE_EVENT


def test_step_mapping_order_does_not_change_result(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    reversed_state = dataclasses.replace(
        state, steps=dict(reversed(list(state.steps.items())))
    )
    event = make_event("a_done")
    assert apply(graph_ab, state, event, T0) == apply(
        graph_ab, reversed_state, event, T0
    )
