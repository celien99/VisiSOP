import copy
from datetime import timedelta

from contracts.enums import ProcessingResult, ReasonCode

from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import StepStatus
from tests.domain.sop.conftest import T0, make_event


def test_initial_state_activates_start_steps(graph_ab) -> None:
    state = initial_state(graph_ab, "exec-1", T0)
    assert state.steps["a"].status is StepStatus.ACTIVE
    assert state.steps["b"].status is StepStatus.PENDING
    assert state.steps["a"].deadline_at is not None


def test_event_completes_active_step_and_activates_next(graph_ab) -> None:
    result = apply(
        graph_ab,
        initial_state(graph_ab, "e", T0),
        make_event("a_done"),
        T0 + timedelta(seconds=1),
    )
    transitions = {t.step_key: t for t in result.step_transitions}
    assert transitions["a"].to_status is StepStatus.COMPLETED
    assert transitions["b"].to_status is StepStatus.ACTIVE


def test_atomic_pending_to_completed(graph_ab, state_with_a_completed) -> None:
    result = apply(graph_ab, state_with_a_completed, make_event("b_done"), T0)
    assert result.step_transitions[0].from_status is StepStatus.PENDING
    assert result.step_transitions[0].to_status is StepStatus.COMPLETED


def test_out_of_order_event_does_not_advance(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0), make_event("b_done"), T0)
    assert result.step_transitions == ()
    assert result.alarms[0].reason_code is ReasonCode.OUT_OF_ORDER


def test_unknown_event_type_is_unexpected(graph_ab) -> None:
    result = apply(
        graph_ab, initial_state(graph_ab, "e", T0), make_event("mystery"), T0
    )
    assert result.alarms[0].reason_code is ReasonCode.UNEXPECTED_STEP


def test_low_confidence_does_not_complete(graph_ab) -> None:
    result = apply(
        graph_ab,
        initial_state(graph_ab, "e", T0),
        make_event("a_done", confidence=0.5),
        T0,
    )
    assert all(t.to_status is not StepStatus.COMPLETED for t in result.step_transitions)
    assert result.evidence_updates[0].event.accepted is False


def test_same_event_id_is_duplicate(graph_ab, state_with_a_done) -> None:
    result = apply(graph_ab, state_with_a_done, make_event("a_done"), T0)
    assert result.processing_result is ProcessingResult.DUPLICATE
    assert result.step_transitions == ()


def test_apply_is_deterministic(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    event = make_event("a_done")
    assert apply(graph_ab, state, event, T0) == apply(graph_ab, state, event, T0)


def test_apply_does_not_mutate_input(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    snapshot = copy.deepcopy(state)
    apply(graph_ab, state, make_event("a_done"), T0)
    assert state == snapshot
