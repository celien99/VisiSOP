import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any

import pytest

from app.domain.sop.compiler import compile_spec
from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import (
    ExecutionState,
    ExecutionStatus,
    SOPGraph,
    StepState,
    StepStatus,
)
from contracts.enums import ReasonCode
from contracts.events import ModelRef, RoutedSOPEvent
from sop_dsl.schema import SOPSpec

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def step_spec(
    key: str,
    *,
    depends_on: Iterable[str] = (),
    timeout_ms: int | None = 1000,
    required: bool = True,
    completion: dict[str, Any] | None = None,
    skip_if: dict[str, Any] | None = None,
    join_policy: dict[str, Any] | str | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "key": key,
        "name": key.upper(),
        "type": "ACTION",
        "depends_on": list(depends_on),
        "timeout_ms": timeout_ms,
        "completion": completion or event_rule(f"{key}_done"),
    }
    if not required:
        spec["required"] = False
    if skip_if is not None:
        spec["skip_if"] = skip_if
    if join_policy is not None:
        spec["join_policy"] = join_policy
    if failure is not None:
        spec["failure"] = failure
    return spec


def event_rule(
    event_type: str,
    *,
    min_confidence: float = 0.9,
    stable_for_ms: int = 0,
    within_ms: int | None = None,
    source_camera_role: str | None = None,
) -> dict[str, Any]:
    condition: dict[str, Any] = {
        "event_type": event_type,
        "min_confidence": min_confidence,
        "stable_for_ms": stable_for_ms,
    }
    if within_ms is not None:
        condition["within_ms"] = within_ms
    if source_camera_role is not None:
        condition["source_camera_role"] = source_camera_role
    return {"mode": "EVENT_RULE", "all": [condition]}


def make_spec(
    steps: Iterable[dict[str, Any]], *, sop_key: str = "s", version: int = 1
) -> SOPSpec:
    return SOPSpec.model_validate(
        {
            "schema_version": "1.0",
            "sop_key": sop_key,
            "version": version,
            "name": sop_key,
            "steps": list(steps),
        }
    )


def make_graph(
    steps: Iterable[dict[str, Any]], *, known: set[str] | None = None
) -> SOPGraph:
    return compile_spec(make_spec(steps), known_event_types=known)


def make_event(
    event_type: str,
    *,
    event_id: str = "e-1",
    confidence: float = 0.95,
    occurred_at: datetime = T0,
    camera_role: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> RoutedSOPEvent:
    return RoutedSOPEvent(
        schema_version="1.0",
        event_id=event_id,
        event_type=event_type,
        station_id="st-01",
        camera_id="cam-01",
        camera_role=camera_role,
        occurred_at=occurred_at,
        emitted_at=occurred_at,
        frame_seq=0,
        confidence=confidence,
        model=ModelRef(name="test", version="1"),
        attributes=attributes or {},
        execution_id="e",
        resolution_method="ACTIVE_EXECUTION_WINDOW",
        resolved_at=occurred_at,
        resolver_rule_version="1",
        candidate_ids=("e",),
    )


def make_state(
    graph: SOPGraph,
    *,
    status: ExecutionStatus = ExecutionStatus.RUNNING,
    steps: Mapping[str, StepState] | None = None,
    execution_id: str = "e",
) -> ExecutionState:
    if steps is None:
        state = initial_state(graph, execution_id, T0)
        if status is ExecutionStatus.RUNNING:
            return state
        return dataclasses.replace(state, status=status)
    return ExecutionState(
        execution_id=execution_id,
        status=status,
        steps=MappingProxyType(dict(steps)),
        started_at=T0,
    )


def advance(
    graph: SOPGraph,
    state: ExecutionState,
    events: Iterable[RoutedSOPEvent],
    now: datetime = T0,
) -> ExecutionState:
    for event in events:
        result = apply(graph, state, event, now)
        steps = dict(state.steps)
        for update in result.evidence_updates:
            step = steps[update.step_key]
            steps[update.step_key] = dataclasses.replace(
                step, matched_events=(*step.matched_events, update.event)
            )
        for transition in result.step_transitions:
            step = steps[transition.step_key]
            updates: dict[str, Any] = {
                "status": transition.to_status,
                "reason_code": transition.reason_code,
            }
            if transition.to_status is StepStatus.ACTIVE:
                timeout_ms = graph.steps[transition.step_key].timeout_ms
                updates["activated_at"] = now
                updates["deadline_at"] = (
                    now + timedelta(milliseconds=timeout_ms)
                    if timeout_ms is not None
                    else None
                )
            if transition.reason_code is ReasonCode.AUTO_SKIP:
                updates["skipped_reason"] = transition.detail
            steps[transition.step_key] = dataclasses.replace(step, **updates)
        execution_transition = result.execution_transition
        state = dataclasses.replace(
            state,
            steps=MappingProxyType(steps),
            status=(
                execution_transition.to_status
                if execution_transition is not None
                else state.status
            ),
        )
    return state


@pytest.fixture
def graph_ab() -> SOPGraph:
    return make_graph([step_spec("a"), step_spec("b", depends_on=("a",))])


@pytest.fixture
def any_graph() -> SOPGraph:
    return make_graph(
        [
            step_spec(
                "a",
                completion={
                    "mode": "EVENT_RULE",
                    "any": [
                        {"event_type": "a_done", "min_confidence": 0.9},
                        {"event_type": "b_done", "min_confidence": 0.9},
                    ],
                },
            )
        ]
    )


@pytest.fixture
def not_graph() -> SOPGraph:
    return make_graph(
        [
            step_spec(
                "a",
                completion={
                    "mode": "EVENT_RULE",
                    "all": [{"event_type": "present", "min_confidence": 0.9}],
                    "not": [
                        {"event_type": "part_removed", "min_confidence": 0.9}
                    ],
                },
            )
        ]
    )


@pytest.fixture
def stable_graph() -> SOPGraph:
    return make_graph(
        [step_spec("a", completion=event_rule("present", stable_for_ms=500))]
    )


@pytest.fixture
def state_with_first_event(stable_graph: SOPGraph) -> ExecutionState:
    return advance(
        stable_graph,
        initial_state(stable_graph, "e", T0),
        [make_event("present")],
    )


@pytest.fixture
def within_graph() -> SOPGraph:
    return make_graph(
        [step_spec("a", completion=event_rule("present", within_ms=500))]
    )


@pytest.fixture
def role_graph() -> SOPGraph:
    return make_graph(
        [
            step_spec(
                "a", completion=event_rule("present", source_camera_role="overview")
            )
        ]
    )


@pytest.fixture
def state_with_a_done(graph_ab: SOPGraph) -> ExecutionState:
    return advance(
        graph_ab, initial_state(graph_ab, "e", T0), [make_event("a_done")]
    )


@pytest.fixture
def state_with_a_completed(graph_ab: SOPGraph) -> ExecutionState:
    return make_state(
        graph_ab,
        steps={
            "a": StepState(key="a", status=StepStatus.COMPLETED),
            "b": StepState(key="b"),
        },
    )


@pytest.fixture
def state_with_low_confidence(graph_ab: SOPGraph) -> ExecutionState:
    return advance(
        graph_ab,
        initial_state(graph_ab, "e", T0),
        [make_event("a_done", confidence=0.5)],
    )


@pytest.fixture
def state_with_a_timed_out(graph_ab: SOPGraph) -> ExecutionState:
    return make_state(
        graph_ab,
        steps={
            "a": StepState(key="a", status=StepStatus.TIMED_OUT),
            "b": StepState(key="b"),
        },
    )


@pytest.fixture
def state_completed(graph_ab: SOPGraph) -> ExecutionState:
    return make_state(
        graph_ab,
        status=ExecutionStatus.COMPLETED,
        steps={
            "a": StepState(key="a", status=StepStatus.COMPLETED),
            "b": StepState(key="b", status=StepStatus.COMPLETED),
        },
    )


@pytest.fixture
def state_all_completed(graph_ab: SOPGraph) -> ExecutionState:
    return make_state(
        graph_ab,
        steps={
            "a": StepState(key="a", status=StepStatus.COMPLETED),
            "b": StepState(key="b", status=StepStatus.COMPLETED),
        },
    )


@pytest.fixture
def skip_graph() -> SOPGraph:
    return make_graph(
        [
            step_spec("a"),
            step_spec(
                "optional",
                depends_on=("a",),
                required=False,
                skip_if={"all_steps_completed": ["a"]},
            ),
            step_spec("after", depends_on=("optional",)),
        ]
    )


@pytest.fixture
def skip_event_graph() -> SOPGraph:
    return make_graph(
        [
            step_spec(
                "optional",
                required=False,
                skip_if={"event_type": "skip_now"},
            ),
            step_spec("after", depends_on=("optional",)),
        ]
    )


@pytest.fixture
def failure_graph() -> SOPGraph:
    return make_graph(
        [
            step_spec(
                "a",
                failure={
                    "event_type": "bad_part",
                    "reason_code": "EVIDENCE_MISSING",
                },
            )
        ]
    )


@pytest.fixture
def state_with_a_failed(graph_ab: SOPGraph) -> ExecutionState:
    return make_state(
        graph_ab,
        steps={
            "a": StepState(key="a", status=StepStatus.FAILED),
            "b": StepState(key="b"),
        },
    )
