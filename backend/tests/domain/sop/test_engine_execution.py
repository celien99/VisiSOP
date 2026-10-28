from contracts.enums import ReasonCode

from app.domain.sop.engine import apply, derive_execution_status, initial_state
from app.domain.sop.model import ExecutionStatus, StepStatus
from tests.domain.sop.conftest import T0, make_event


def test_execution_completes_when_all_steps_terminal(
    graph_ab, state_all_completed
) -> None:
    assert (
        derive_execution_status(
            graph_ab, state_all_completed.steps, ExecutionStatus.RUNNING
        )
        is ExecutionStatus.COMPLETED
    )


def test_failed_required_step_blocks_completion(graph_ab, state_with_a_failed) -> None:
    assert (
        derive_execution_status(
            graph_ab, state_with_a_failed.steps, ExecutionStatus.RUNNING
        )
        is ExecutionStatus.NEEDS_REVIEW
    )


def test_failure_rule_marks_step_failed(failure_graph) -> None:
    result = apply(
        failure_graph,
        initial_state(failure_graph, "e", T0),
        make_event("bad_part"),
        T0,
    )
    assert result.step_transitions[0].to_status is StepStatus.FAILED
    assert result.step_transitions[0].reason_code is ReasonCode.EVIDENCE_MISSING


def test_alarm_categories_are_set(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0), make_event("b_done"), T0)
    assert result.alarms[0].category == "PROCESS_COMPLIANCE"
    assert result.alarms[0].severity == "HIGH"
