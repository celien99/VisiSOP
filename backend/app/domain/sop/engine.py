import dataclasses
from collections.abc import Mapping
from datetime import datetime, timedelta
from types import MappingProxyType

from contracts.enums import ProcessingResult, ReasonCode
from contracts.events import RoutedSOPEvent
from sop_dsl.schema import (
    CompletionSpec,
    EventCondition,
    EventRuleCompletion,
    JoinPolicy,
    StateRuleCompletion,
)

from app.domain.sop.model import (
    AlarmIntent,
    CompiledStep,
    EvidenceUpdate,
    ExecutionState,
    ExecutionStatus,
    ExecutionTransition,
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
_COMPLETE_STEP_STATUSES = frozenset({StepStatus.COMPLETED, StepStatus.SKIPPED})
_TERMINAL_STEP_STATUSES = frozenset(
    {
        StepStatus.COMPLETED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
        StepStatus.TIMED_OUT,
        StepStatus.NEEDS_REVIEW,
    }
)


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
    if step.failure is not None and step.failure.event_type == event_type:
        return True
    if step.skip_if is not None and step.skip_if.event_type == event_type:
        return True
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


def _conditions_for_event(
    step: CompiledStep, event_type: str
) -> tuple[EventCondition, ...]:
    rule = _event_rule(step)
    if rule is None:
        return ()
    return tuple(
        condition
        for condition in (*rule.all, *rule.any, *rule.not_)
        if condition.event_type == event_type
    )


def _single_event_matches(
    condition: EventCondition, event: MatchedEvent, activated_at: datetime | None
) -> bool:
    if event.event_type != condition.event_type:
        return False
    if event.confidence < condition.min_confidence:
        return False
    if (
        condition.source_camera_role is not None
        and event.camera_role != condition.source_camera_role
    ):
        return False
    if condition.within_ms is not None and (
        activated_at is None
        or event.occurred_at
        > activated_at + timedelta(milliseconds=condition.within_ms)
    ):
        return False
    return True


def _condition_matches(
    condition: EventCondition,
    events: tuple[MatchedEvent, ...],
    activated_at: datetime | None,
) -> bool:
    eligible = [
        event
        for event in events
        if event.accepted and _single_event_matches(condition, event, activated_at)
    ]
    if not eligible:
        return False
    if condition.stable_for_ms <= 0:
        return True
    times = [event.occurred_at for event in eligible]
    return max(times) - min(times) >= timedelta(milliseconds=condition.stable_for_ms)


def _rule_satisfied(
    completion: CompletionSpec,
    events: tuple[MatchedEvent, ...],
    activated_at: datetime | None,
) -> bool:
    if not isinstance(completion, EventRuleCompletion):
        return False
    if not completion.all and not completion.any:
        return False
    all_satisfied = all(
        _condition_matches(condition, events, activated_at)
        for condition in completion.all
    )
    any_satisfied = (
        any(
            _condition_matches(condition, events, activated_at)
            for condition in completion.any
        )
        if completion.any
        else True
    )
    not_satisfied = not any(
        _condition_matches(condition, events, activated_at)
        for condition in completion.not_
    )
    return all_satisfied and any_satisfied and not_satisfied


def _dependencies_satisfied(step: CompiledStep, steps: Mapping[str, StepState]) -> bool:
    return all(steps[dep].status in _SATISFIED_STEP_STATUSES for dep in step.depends_on)


def _settle_skip_reason(
    step: CompiledStep, steps: Mapping[str, StepState]
) -> str | None:
    skip_if = step.skip_if
    if skip_if is None or not skip_if.all_steps_completed:
        return None
    if all(
        steps[ref].status in _SATISFIED_STEP_STATUSES
        for ref in skip_if.all_steps_completed
    ):
        return "all_steps_completed:" + ",".join(skip_if.all_steps_completed)
    return None


def _state_rule_satisfied(
    completion: CompletionSpec, steps: Mapping[str, StepState]
) -> bool:
    if not isinstance(completion, StateRuleCompletion):
        return False
    if completion.all_steps_completed and not all(
        steps[key].status in _SATISFIED_STEP_STATUSES
        for key in completion.all_steps_completed
    ):
        return False
    if completion.any_steps_completed and not any(
        steps[key].status in _SATISFIED_STEP_STATUSES
        for key in completion.any_steps_completed
    ):
        return False
    return bool(completion.all_steps_completed or completion.any_steps_completed)


def _join_status(
    policy: JoinPolicy, steps: Mapping[str, StepState], depends_on: tuple[str, ...]
) -> tuple[StepStatus, ReasonCode | None]:
    satisfied = sum(
        1 for key in depends_on if steps[key].status in _SATISFIED_STEP_STATUSES
    )
    if policy.type == "ALL_REQUIRED":
        complete = satisfied == len(depends_on)
    else:
        complete = policy.n is not None and satisfied >= policy.n
    if complete:
        return StepStatus.COMPLETED, None
    return StepStatus.NEEDS_REVIEW, ReasonCode.EVIDENCE_MISSING


def _join_dependencies_terminal(
    step: CompiledStep, steps: Mapping[str, StepState]
) -> bool:
    return all(steps[key].status in _TERMINAL_STEP_STATUSES for key in step.depends_on)


def _activate_pass(
    graph: SOPGraph, steps: dict[str, StepState], now: datetime
) -> list[StepTransition]:
    transitions: list[StepTransition] = []
    for key in graph.order:
        step_state = steps[key]
        if step_state.status is not StepStatus.PENDING:
            continue
        compiled = graph.steps[key]
        if compiled.join_policy is not None:
            ready = _join_dependencies_terminal(compiled, steps)
        else:
            ready = _dependencies_satisfied(compiled, steps)
        if not ready:
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
    return transitions


def activate_ready(
    graph: SOPGraph, state: ExecutionState, now: datetime
) -> list[StepTransition]:
    """Activation pass for callers that resolved a step outside the event stream."""
    return _activate_pass(graph, dict(state.steps), now)


def _settle(
    graph: SOPGraph, steps: dict[str, StepState], now: datetime
) -> list[StepTransition]:
    transitions: list[StepTransition] = []
    for _ in range(len(graph.steps) + 1):
        changed = False

        for key in graph.order:
            step_state = steps[key]
            if step_state.status is not StepStatus.PENDING:
                continue
            compiled = graph.steps[key]
            skip_reason = _settle_skip_reason(compiled, steps)
            if skip_reason is None:
                continue
            steps[key] = dataclasses.replace(
                step_state,
                status=StepStatus.SKIPPED,
                reason_code=ReasonCode.AUTO_SKIP,
                skipped_reason=skip_reason,
            )
            transitions.append(
                StepTransition(
                    step_key=key,
                    from_status=StepStatus.PENDING,
                    to_status=StepStatus.SKIPPED,
                    reason_code=ReasonCode.AUTO_SKIP,
                    detail=skip_reason,
                )
            )
            changed = True

        activations = _activate_pass(graph, steps, now)
        if activations:
            transitions.extend(activations)
            changed = True

        for key in graph.order:
            step_state = steps[key]
            compiled = graph.steps[key]
            if (
                step_state.status is not StepStatus.ACTIVE
                or compiled.join_policy is not None
                or not _state_rule_satisfied(compiled.completion, steps)
            ):
                continue
            steps[key] = dataclasses.replace(step_state, status=StepStatus.COMPLETED)
            transitions.append(
                StepTransition(
                    step_key=key,
                    from_status=StepStatus.ACTIVE,
                    to_status=StepStatus.COMPLETED,
                )
            )
            changed = True

        for key in graph.order:
            step_state = steps[key]
            compiled = graph.steps[key]
            if (
                step_state.status is not StepStatus.ACTIVE
                or compiled.join_policy is None
            ):
                continue
            to_status, reason_code = _join_status(
                compiled.join_policy, steps, compiled.depends_on
            )
            steps[key] = dataclasses.replace(
                step_state, status=to_status, reason_code=reason_code
            )
            transitions.append(
                StepTransition(
                    step_key=key,
                    from_status=StepStatus.ACTIVE,
                    to_status=to_status,
                    reason_code=reason_code,
                )
            )
            changed = True

        if not changed:
            return transitions

    raise RuntimeError("settle did not converge")


def _alarm(
    reason_code: ReasonCode,
    event: RoutedSOPEvent,
    step_key: str | None,
    *,
    category: str = "PROCESS_COMPLIANCE",
    severity: str = "HIGH",
) -> AlarmIntent:
    return AlarmIntent(
        category=category,
        severity=severity,
        reason_code=reason_code,
        step_key=step_key,
        source_event_id=event.event_id,
        message=f"{reason_code}: {event.event_type} ({event.event_id})",
    )


def _is_low_confidence(step: CompiledStep, event: MatchedEvent) -> bool:
    return any(
        condition.event_type == event.event_type
        and event.confidence < condition.min_confidence
        for condition in _conditions_for_event(step, event.event_type)
    )


def derive_execution_status(
    graph: SOPGraph,
    steps: Mapping[str, StepState],
    current: ExecutionStatus,
) -> ExecutionStatus:
    if any(steps[key].status is StepStatus.NEEDS_REVIEW for key in graph.order):
        return ExecutionStatus.NEEDS_REVIEW
    if any(
        graph.steps[key].required
        and steps[key].status in (StepStatus.FAILED, StepStatus.TIMED_OUT)
        for key in graph.order
    ):
        return ExecutionStatus.NEEDS_REVIEW
    if all(
        (not graph.steps[key].required or steps[key].status in _COMPLETE_STEP_STATUSES)
        and steps[key].status in _TERMINAL_STEP_STATUSES
        for key in graph.order
    ):
        return ExecutionStatus.COMPLETED
    return current


def _seen_event(state: ExecutionState, event_id: str) -> bool:
    return any(
        matched.event_id == event_id
        for step_state in state.steps.values()
        for matched in step_state.matched_events
    )


def timed_out(
    graph: SOPGraph, state: ExecutionState, now: datetime
) -> list[StepTransition]:
    if state.status in (
        ExecutionStatus.PAUSED,
        ExecutionStatus.COMPLETED,
        ExecutionStatus.ABORTED,
    ):
        return []

    steps = dict(state.steps)
    transitions: list[StepTransition] = []
    for key in graph.order:
        step_state = steps[key]
        if step_state.status is not StepStatus.ACTIVE:
            continue
        if step_state.deadline_at is None or step_state.deadline_at > now:
            continue
        if any(not event.accepted for event in step_state.matched_events):
            to_status = StepStatus.NEEDS_REVIEW
            reason_code = ReasonCode.LOW_CONFIDENCE
        else:
            to_status = StepStatus.TIMED_OUT
            reason_code = ReasonCode.TIMEOUT
        steps[key] = dataclasses.replace(
            step_state, status=to_status, reason_code=reason_code
        )
        transitions.append(
            StepTransition(
                step_key=key,
                from_status=StepStatus.ACTIVE,
                to_status=to_status,
                reason_code=reason_code,
            )
        )

    if transitions:
        transitions.extend(_settle(graph, steps, now))
    return transitions


def apply(
    graph: SOPGraph,
    state: ExecutionState,
    event: RoutedSOPEvent,
    now: datetime,
) -> TransitionResult:
    if state.status in _TERMINAL_EXECUTION_STATUSES:
        return TransitionResult(
            reason_code=ReasonCode.LATE_EVENT,
            detail="execution_terminal",
        )

    if _seen_event(state, event.event_id):
        return TransitionResult(
            processing_result=ProcessingResult.DUPLICATE,
            detail=f"duplicate event_id: {event.event_id}",
        )

    reference_keys = [
        key
        for key in graph.order
        if _references_event(graph.steps[key], event.event_type)
    ]
    if not reference_keys:
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

    for key in reference_keys:
        compiled = graph.steps[key]
        step_state = steps[key]
        matched = dataclasses.replace(
            candidate,
            accepted=any(
                _single_event_matches(condition, candidate, step_state.activated_at)
                for condition in _conditions_for_event(compiled, event.event_type)
            ),
        )

        skip_if = compiled.skip_if
        if (
            step_state.status in (StepStatus.ACTIVE, StepStatus.PENDING)
            and skip_if is not None
            and skip_if.event_type == event.event_type
        ):
            detail = f"event_type:{event.event_type}"
            updates.append(EvidenceUpdate(step_key=key, event=matched))
            steps[key] = dataclasses.replace(
                step_state,
                status=StepStatus.SKIPPED,
                reason_code=ReasonCode.AUTO_SKIP,
                skipped_reason=detail,
            )
            transitions.append(
                StepTransition(
                    step_key=key,
                    from_status=step_state.status,
                    to_status=StepStatus.SKIPPED,
                    reason_code=ReasonCode.AUTO_SKIP,
                    matched_event_ids=(event.event_id,),
                    detail=detail,
                )
            )
            continue

        if step_state.status is StepStatus.PENDING and not _dependencies_satisfied(
            compiled, steps
        ):
            alarms.append(_alarm(ReasonCode.OUT_OF_ORDER, event, key))
            continue

        updates.append(EvidenceUpdate(step_key=key, event=matched))

        failure = compiled.failure
        if (
            step_state.status is StepStatus.ACTIVE
            and failure is not None
            and failure.event_type == event.event_type
        ):
            steps[key] = dataclasses.replace(
                step_state,
                status=StepStatus.FAILED,
                reason_code=failure.reason_code,
            )
            transitions.append(
                StepTransition(
                    step_key=key,
                    from_status=StepStatus.ACTIVE,
                    to_status=StepStatus.FAILED,
                    reason_code=failure.reason_code,
                    matched_event_ids=(event.event_id,),
                )
            )
            continue

        if step_state.status is StepStatus.COMPLETED:
            continue
        if step_state.status is StepStatus.TIMED_OUT:
            if (
                matched.accepted
                and _trigger_conditions(compiled, event.event_type)
                and _rule_satisfied(
                    compiled.completion,
                    (*step_state.matched_events, matched),
                    step_state.activated_at,
                )
            ):
                steps[key] = dataclasses.replace(
                    step_state,
                    status=StepStatus.NEEDS_REVIEW,
                    reason_code=ReasonCode.LATE_EVENT,
                )
                transitions.append(
                    StepTransition(
                        step_key=key,
                        from_status=StepStatus.TIMED_OUT,
                        to_status=StepStatus.NEEDS_REVIEW,
                        reason_code=ReasonCode.LATE_EVENT,
                        matched_event_ids=(event.event_id,),
                    )
                )
            continue
        if step_state.status not in (StepStatus.ACTIVE, StepStatus.PENDING):
            continue

        if not matched.accepted:
            if _is_low_confidence(compiled, matched):
                alarms.append(
                    _alarm(
                        ReasonCode.LOW_CONFIDENCE,
                        event,
                        key,
                        category="VISION_QUALITY",
                        severity="MEDIUM",
                    )
                )
            continue
        if not _trigger_conditions(compiled, event.event_type):
            continue
        if not _rule_satisfied(
            compiled.completion,
            (*step_state.matched_events, matched),
            step_state.activated_at,
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

    derived = derive_execution_status(graph, steps, state.status)
    return TransitionResult(
        step_transitions=tuple(transitions),
        evidence_updates=tuple(updates),
        execution_transition=(
            ExecutionTransition(from_status=state.status, to_status=derived)
            if derived is not state.status
            else None
        ),
        alarms=tuple(alarms),
        reason_code=(alarms[0].reason_code if alarms and not transitions else None),
    )
