from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import StepStatus
from tests.domain.sop.conftest import (
    T0,
    make_event,
    state_with_left_done,
    state_with_left_failed,
)


def test_join_waits_for_all_dependencies(parallel_join_graph) -> None:
    state = initial_state(parallel_join_graph, "e", T0)
    after_left = apply(parallel_join_graph, state, make_event("left_done"), T0)
    assert all(t.step_key != "join" for t in after_left.step_transitions)


def test_all_required_completes_when_both_done(parallel_join_graph) -> None:
    state = state_with_left_done(parallel_join_graph)
    result = apply(
        parallel_join_graph,
        state,
        make_event("right_done", event_id="e-2"),
        T0,
    )
    assert any(
        t.step_key == "join" and t.to_status is StepStatus.COMPLETED
        for t in result.step_transitions
    )


def test_any_of_n_completes_with_one_success(any_join_graph) -> None:
    state = state_with_left_done(any_join_graph)
    result = apply(
        any_join_graph,
        state,
        make_event("right_fail", event_id="e-2"),
        T0,
    )
    assert any(
        t.step_key == "join" and t.to_status is StepStatus.COMPLETED
        for t in result.step_transitions
    )


def test_any_of_n_not_met_goes_to_review(any_join_graph) -> None:
    state = state_with_left_failed(any_join_graph)
    result = apply(
        any_join_graph,
        state,
        make_event("right_fail", event_id="e-2"),
        T0,
    )
    assert any(
        t.step_key == "join" and t.to_status is StepStatus.NEEDS_REVIEW
        for t in result.step_transitions
    )


def test_state_rule_checkpoint_completes(parallel_join_graph) -> None:
    state = state_with_left_done(parallel_join_graph)
    result = apply(
        parallel_join_graph,
        state,
        make_event("right_done", event_id="e-2"),
        T0,
    )
    assert any(
        t.step_key == "check" and t.to_status is StepStatus.COMPLETED
        for t in result.step_transitions
    )
