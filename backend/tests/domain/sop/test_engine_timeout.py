import dataclasses
from datetime import timedelta

from contracts.enums import ReasonCode

from app.domain.sop.engine import apply, initial_state, timed_out
from app.domain.sop.model import ExecutionStatus, StepStatus
from tests.domain.sop.conftest import T0, make_event


def test_timeout_marks_step_timed_out(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    transitions = timed_out(graph_ab, state, T0 + timedelta(milliseconds=1001))
    assert transitions[0].step_key == "a"
    assert transitions[0].to_status is StepStatus.TIMED_OUT
    assert transitions[0].reason_code is ReasonCode.TIMEOUT


def test_no_timeout_before_deadline(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    assert timed_out(graph_ab, state, T0 + timedelta(milliseconds=999)) == []


def test_paused_execution_does_not_timeout(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    paused = dataclasses.replace(state, status=ExecutionStatus.PAUSED)
    assert timed_out(graph_ab, paused, T0 + timedelta(seconds=10)) == []


def test_low_confidence_timeout_goes_to_review(
    graph_ab, state_with_low_confidence
) -> None:
    transitions = timed_out(
        graph_ab, state_with_low_confidence, T0 + timedelta(milliseconds=1001)
    )
    assert transitions[0].to_status is StepStatus.NEEDS_REVIEW
    assert transitions[0].reason_code is ReasonCode.LOW_CONFIDENCE


def test_late_event_after_timeout_does_not_complete(
    graph_ab, state_with_a_timed_out
) -> None:
    result = apply(graph_ab, state_with_a_timed_out, make_event("a_done"), T0)
    assert all(t.to_status is not StepStatus.COMPLETED for t in result.step_transitions)
