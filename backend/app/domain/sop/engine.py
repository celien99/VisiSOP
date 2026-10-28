import dataclasses
from collections.abc import Mapping
from datetime import datetime, timedelta
from types import MappingProxyType

from contracts.enums import ProcessingResult, ReasonCode
from contracts.events import RoutedSOPEvent
from sop_dsl.schema import CompletionSpec, EventCondition, EventRuleCompletion

from app.domain.sop.model import (
    AlarmIntent,
    CompiledStep,
    EvidenceUpdate,
    ExecutionState,
    ExecutionStatus,
    MatchedEvent,
    SOPGraph,
    StepState,
    StepStatus,
    StepTransition,
    TransitionResult,
)

_TERMINAL_EXECUTION_STATUSES = frozenset(
    {ExecutionStatus.COMPLETED, ExecutionStatus.ABORTED}
)
_SATISFIED_STEP_STATUSES = frozenset({StepStatus.COMPLETED, StepStatus.SKIPPED})


def _deadline(now: datetime, timeout_ms: int | None) -> datetime | None:
    if timeout_ms is None:
        return None
    return now + timedelta(milliseconds=timeout_ms)


def initial_state(graph: SOPGraph, execution_id: str, now: datetime) -> ExecutionState:
    steps: dict[str, StepState] = {}
    for key in graph.order:
        compiled = graph.steps[key]
        if key in graph.start_steps:
            steps[key] = StepState(
                key=key,
                status=StepStatus.ACTIVE,
                activated_at=now,
                deadline_at=_deadline(now, compiled.timeout_ms),
            )
        else:
            steps[key] = StepState(key=key)
    return ExecutionState(
        execution_id=execution_id,
        status=ExecutionStatus.RUNNING,
        steps=MappingProxyType(steps),
        started_at=now,
    )


def _matched_event(event: RoutedSOPEvent, *, accepted: bool) -> MatchedEvent:
    return MatchedEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        confidence=event.confidence,
        occurred_at=event.occurred_at,
        camera_id=event.camera_id,
        camera_role=event.camera_role,
        correlation_key=event.correlation_key,
        accepted=accepted,
    )


def _event_rule(step: CompiledStep) -> EventRuleCompletion | None:
    completion = step.completion
    return completion if isinstance(completion, EventRuleCompletion) else None


def _references_event(step: CompiledStep, event_type: str) -> bool:
    rule = _event_rule(step)
    if rule is None:
        return False
    return any(
        condition.event_type == event_type
        for condition in (*rule.all, *rule.any, *rule.not_)
    )


def _trigger_conditions(
    step: CompiledStep, event_type: str
) -> tuple[EventCondition, ...]:
    rule = _event_rule(step)
    if rule is None:
        return ()
    return tuple(
        condition
        for condition in (*rule.all, *rule.any)
        if condition.event_type == event_type
    )


def _condition_accepts(condition: EventCondition, event: MatchedEvent) -> bool:
    return (
        event.event_type == condition.event_type
        and event.confidence >= condition.min_confidence
    )


def _all_satisfied(
    completion: CompletionSpec, events: tuple[MatchedEvent, ...]
) -> bool:
    if not isinstance(completion, EventRuleCompletion) or not completion.all:
        return False
    accepted = tuple(event for event in events if event.accepted)
    return all(
        any(_condition_accepts(condition, event) for event in accepted)
        for condition in completion.all
    )


def _dependencies_satisfied(step: CompiledStep, steps: Mapping[str, StepState]) -> bool:
    return all(steps[dep].status in _SATISFIED_STEP_STATUSES for dep in step.depends_on)


def _settle(
    graph: SOPGraph, steps: dict[str, StepState], now: datetime
) -> list[StepTransition]:
    transitions: list[StepTransition] = []
    changed = True
    while changed:
        changed = False
        for key in graph.order:
            step_state = steps[key]
            if step_state.status is not StepStatus.PENDING:
                continue
            compiled = graph.steps[key]
            if not _dependencies_satisfied(compiled, steps):
                continue
            steps[key] = dataclasses.replace(
                step_state,
                status=StepStatus.ACTIVE,
                activated_at=now,
                deadline_at=_deadline(now, compiled.timeout_ms),
            )
            transitions.append(
                StepTransition(
                    step_key=key,
                    from_status=StepStatus.PENDING,
                    to_status=StepStatus.ACTIVE,
                )
            )
            changed = True
    return transitions


def _alarm(
    reason_code: ReasonCode, event: RoutedSOPEvent, step_key: str | None
) -> AlarmIntent:
    return AlarmIntent(
        category="PROCESS_COMPLIANCE",
        severity="MEDIUM",
        reason_code=reason_code,
        step_key=step_key,
        source_event_id=event.event_id,
        message=f"{reason_code}: {event.event_type} ({event.event_id})",
    )


def _seen_event(state: ExecutionState, event_id: str) -> bool:
    return any(
        matched.event_id == event_id
        for step_state in state.steps.values()
        for matched in step_state.matched_events
    )


def apply(
    graph: SOPGraph,
    state: ExecutionState,
    event: RoutedSOPEvent,
    now: datetime,
) -> TransitionResult:
    if state.status in _TERMINAL_EXECUTION_STATUSES:
        return TransitionResult()

    if _seen_event(state, event.event_id):
        return TransitionResult(
            processing_result=ProcessingResult.DUPLICATE,
            detail=f"duplicate event_id: {event.event_id}",
        )

    references = [
        (key, _trigger_conditions(graph.steps[key], event.event_type))
        for key in graph.order
        if _references_event(graph.steps[key], event.event_type)
    ]
    if not references:
        alarm = _alarm(ReasonCode.UNEXPECTED_STEP, event, None)
        return TransitionResult(
            alarms=(alarm,),
            reason_code=ReasonCode.UNEXPECTED_STEP,
            detail=f"no step references event type: {event.event_type}",
        )

    steps = dict(state.steps)
    updates: list[EvidenceUpdate] = []
    transitions: list[StepTransition] = []
    alarms: list[AlarmIntent] = []

    candidate = _matched_event(event, accepted=False)
    for key, conditions in references:
        if not conditions:
            continue
        accepted = any(
            _condition_accepts(condition, candidate) for condition in conditions
        )
        matched = dataclasses.replace(candidate, accepted=accepted)
        step_state = steps[key]
        compiled = graph.steps[key]

        if step_state.status not in (StepStatus.ACTIVE, StepStatus.PENDING):
            continue
        if step_state.status is StepStatus.PENDING and not _dependencies_satisfied(
            compiled, steps
        ):
            alarms.append(_alarm(ReasonCode.OUT_OF_ORDER, event, key))
            continue

        updates.append(EvidenceUpdate(step_key=key, event=matched))
        if not accepted:
            continue
        if not _all_satisfied(
            compiled.completion, (*step_state.matched_events, matched)
        ):
            continue

        steps[key] = dataclasses.replace(step_state, status=StepStatus.COMPLETED)
        transitions.append(
            StepTransition(
                step_key=key,
                from_status=step_state.status,
                to_status=StepStatus.COMPLETED,
                matched_event_ids=(event.event_id,),
            )
        )

    if transitions:
        transitions.extend(_settle(graph, steps, now))

    return TransitionResult(
        step_transitions=tuple(transitions),
        evidence_updates=tuple(updates),
        alarms=tuple(alarms),
        reason_code=(alarms[0].reason_code if alarms and not transitions else None),
    )
