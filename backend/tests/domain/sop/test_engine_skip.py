from datetime import timedelta

from contracts.enums import ReasonCode

from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import StepStatus
from tests.domain.sop.conftest import T0, advance, make_event


def test_skip_by_completed_steps(skip_graph) -> None:
    result = apply(
        skip_graph,
        initial_state(skip_graph, "e", T0),
        make_event("a_done"),
        T0 + timedelta(seconds=1),
    )
    skipped = next(t for t in result.step_transitions if t.step_key == "optional")
    assert skipped.to_status is StepStatus.SKIPPED
    assert skipped.reason_code is ReasonCode.AUTO_SKIP


def test_skip_by_event(skip_event_graph) -> None:
    result = apply(
        skip_event_graph,
        initial_state(skip_event_graph, "e", T0),
        make_event("skip_now"),
        T0,
    )
    skipped = next(t for t in result.step_transitions if t.step_key == "optional")
    assert skipped.to_status is StepStatus.SKIPPED


def test_skip_reason_is_recorded(skip_graph) -> None:
    state = advance(
        skip_graph,
        initial_state(skip_graph, "e", T0),
        [make_event("a_done")],
    )
    assert state.steps["optional"].skipped_reason == "all_steps_completed:a"


def test_skipped_step_unlocks_downstream(skip_graph) -> None:
    result = apply(
        skip_graph,
        initial_state(skip_graph, "e", T0),
        make_event("a_done"),
        T0 + timedelta(seconds=1),
    )
    assert any(
        t.step_key == "after" and t.to_status is StepStatus.ACTIVE
        for t in result.step_transitions
    )
