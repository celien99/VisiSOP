import dataclasses
from datetime import datetime, timedelta
from types import MappingProxyType
from uuid import uuid4

from contracts.enums import (
    AlarmCategory,
    AlarmSeverity,
    MessageType,
    ReasonCode,
    ReviewDecision,
)
from sop_dsl.schema import StepType
from sqlmodel import Session, col, select

from app.api.schemas.evidence import EvidenceRead
from app.api.schemas.execution import (
    ExecutionDetailRead,
    ExecutionSummaryRead,
    MatchedEventRead,
    StepRead,
    TimelineItemRead,
    TimelineItemType,
)
from app.application.alarm_service import alarm_dedup_key, upsert_alarm
from app.application.audit import write_audit
from app.application.graph_cache import load_graph
from app.application.outbox import write_outbox
from app.application.sop_service import ordered_step_definitions
from app.application.state_codec import matched_from_json, state_from_rows
from app.application.station_service import StationNotFound, execution_summary_for
from app.core.config import settings
from app.domain.sop.engine import (
    activate_ready,
    derive_execution_status,
    initial_state,
)
from app.domain.sop.model import (
    AlarmIntent,
    ExecutionStatus,
    SOPGraph,
    StepStatus,
    StepTransition,
)
from app.models import (
    Alarm,
    EventEvidenceLink,
    EvidenceAsset,
    EvidenceStatus,
    SOPDefinition,
    SOPExecution,
    SOPVersion,
    SopVersionStatus,
    Station,
    StepExecution,
    VisionEventRow,
)

_ACTIVE_EXECUTION_STATUSES = (
    ExecutionStatus.RUNNING,
    ExecutionStatus.PAUSED,
    ExecutionStatus.NEEDS_REVIEW,
)
_ACCEPT_WINDOW = timedelta(milliseconds=settings.EXECUTION_ACCEPT_WINDOW_MS)
_TIMELINE_ORDER = {
    TimelineItemType.EVENT: 0,
    TimelineItemType.STEP: 1,
    TimelineItemType.ALARM: 2,
}


class ExecutionNotFound(LookupError):
    pass


class SopVersionNotFound(LookupError):
    pass


class SopNotPublished(ValueError):
    pass


class ExecutionConflict(ValueError):
    pass


class StepNotFound(LookupError):
    pass


class StepNotReviewable(ValueError):
    pass


class InvalidEvidence(ValueError):
    pass


def _load_execution(session: Session, execution_id: str) -> SOPExecution:
    execution = session.get(SOPExecution, execution_id)
    if execution is None:
        raise ExecutionNotFound(execution_id)
    return execution


def _step_rows(session: Session, execution_id: str) -> list[StepExecution]:
    statement = select(StepExecution).where(StepExecution.execution_id == execution_id)
    return list(session.exec(statement).all())


def _status_of(row: StepExecution) -> StepStatus:
    return StepStatus(row.status)


def create_execution(
    session: Session,
    *,
    station_id: str,
    sop_version_id: str,
    workpiece_id: str | None,
    now: datetime,
) -> ExecutionDetailRead:
    station = session.get(Station, station_id)
    if station is None:
        raise StationNotFound(station_id)
    version = session.get(SOPVersion, sop_version_id)
    if version is None:
        raise SopVersionNotFound(sop_version_id)
    if version.status != SopVersionStatus.PUBLISHED:
        raise SopNotPublished(sop_version_id)

    active = session.exec(
        select(SOPExecution).where(
            SOPExecution.station_id == station_id,
            col(SOPExecution.status).in_(_ACTIVE_EXECUTION_STATUSES),
        )
    ).first()
    if active is not None:
        raise ExecutionConflict(active.id)

    graph = load_graph(session, sop_version_id)
    execution = SOPExecution(
        id=str(uuid4()),
        station_id=station_id,
        sop_version_id=sop_version_id,
        workpiece_id=workpiece_id,
        status=ExecutionStatus.RUNNING,
        started_at=now,
        accept_events_until=now + _ACCEPT_WINDOW,
        created_at=now,
    )
    session.add(execution)
    state = initial_state(graph, execution.id, now)
    for key in graph.order:
        step_state = state.steps[key]
        session.add(
            StepExecution(
                execution_id=execution.id,
                step_key=key,
                status=step_state.status,
                activated_at=step_state.activated_at,
                deadline_at=step_state.deadline_at,
                matched_events=[],
                reason_code=step_state.reason_code,
                updated_at=now,
            )
        )

    write_audit(
        session,
        actor="system",
        action="execution.created",
        object_type="execution",
        object_id=execution.id,
        detail={
            "station_id": station_id,
            "sop_version_id": sop_version_id,
            "workpiece_id": workpiece_id,
        },
        now=now,
    )
    write_outbox(
        session,
        message_type=MessageType.EXECUTION_UPDATED,
        station_id=station_id,
        payload={
            "execution_id": execution.id,
            "status": ExecutionStatus.RUNNING.value,
        },
        now=now,
    )
    session.flush()
    return get_execution(session, execution_id=execution.id, now=now)


def pause_execution(
    session: Session, *, execution_id: str, now: datetime
) -> ExecutionDetailRead:
    execution = _load_execution(session, execution_id)
    if ExecutionStatus(execution.status) != ExecutionStatus.RUNNING:
        raise ExecutionConflict(execution.id)
    execution.status = ExecutionStatus.PAUSED
    execution.paused_at = now
    execution.version += 1
    session.add(execution)
    write_audit(
        session,
        actor="system",
        action="execution.paused",
        object_type="execution",
        object_id=execution.id,
        detail={},
        now=now,
    )
    write_outbox(
        session,
        message_type=MessageType.EXECUTION_UPDATED,
        station_id=execution.station_id,
        payload={
            "execution_id": execution.id,
            "status": ExecutionStatus.PAUSED.value,
        },
        now=now,
    )
    session.flush()
    return get_execution(session, execution_id=execution.id, now=now)


def resume_execution(
    session: Session, *, execution_id: str, now: datetime
) -> ExecutionDetailRead:
    execution = _load_execution(session, execution_id)
    if ExecutionStatus(execution.status) != ExecutionStatus.PAUSED:
        raise ExecutionConflict(execution.id)
    paused_at = execution.paused_at or now
    paused_for = now - paused_at
    for row in _step_rows(session, execution.id):
        if _status_of(row) is StepStatus.ACTIVE and row.deadline_at is not None:
            row.deadline_at = row.deadline_at + paused_for
            row.updated_at = now
            session.add(row)
    execution.total_paused_ms += int(paused_for.total_seconds() * 1000)
    execution.status = ExecutionStatus.RUNNING
    execution.paused_at = None
    execution.version += 1
    session.add(execution)
    write_audit(
        session,
        actor="system",
        action="execution.resumed",
        object_type="execution",
        object_id=execution.id,
        detail={"paused_ms": int(paused_for.total_seconds() * 1000)},
        now=now,
    )
    write_outbox(
        session,
        message_type=MessageType.EXECUTION_UPDATED,
        station_id=execution.station_id,
        payload={
            "execution_id": execution.id,
            "status": ExecutionStatus.RUNNING.value,
        },
        now=now,
    )
    session.flush()
    return get_execution(session, execution_id=execution.id, now=now)


def abort_execution(
    session: Session, *, execution_id: str, reason: str, now: datetime
) -> ExecutionDetailRead:
    execution = _load_execution(session, execution_id)
    if ExecutionStatus(execution.status) not in _ACTIVE_EXECUTION_STATUSES:
        raise ExecutionConflict(execution.id)
    execution.status = ExecutionStatus.ABORTED
    execution.finished_at = now
    execution.version += 1
    session.add(execution)
    write_audit(
        session,
        actor="system",
        action="execution.aborted",
        object_type="execution",
        object_id=execution.id,
        detail={"reason": reason},
        now=now,
    )
    write_outbox(
        session,
        message_type=MessageType.EXECUTION_UPDATED,
        station_id=execution.station_id,
        payload={
            "execution_id": execution.id,
            "status": ExecutionStatus.ABORTED.value,
        },
        now=now,
    )
    session.flush()
    return get_execution(session, execution_id=execution.id, now=now)


def _apply_step_row(
    row: StepExecution,
    transition: StepTransition,
    graph: SOPGraph,
    now: datetime,
) -> bool:
    if _status_of(row) != transition.from_status:
        return False
    row.status = transition.to_status
    if transition.reason_code is not None:
        row.reason_code = transition.reason_code
    if transition.to_status is StepStatus.ACTIVE:
        row.activated_at = now
        timeout_ms = graph.steps[transition.step_key].timeout_ms
        row.deadline_at = (
            now + timedelta(milliseconds=timeout_ms) if timeout_ms is not None else None
        )
    row.updated_at = now
    return True


def apply_transitions(
    session: Session,
    *,
    execution: SOPExecution,
    graph: SOPGraph,
    transitions: tuple[StepTransition, ...],
    alarms: tuple[AlarmIntent, ...],
    now: datetime,
    source_event_id: str | None = None,
) -> None:
    rows = {row.step_key: row for row in _step_rows(session, execution.id)}
    applied: list[StepTransition] = []
    for transition in transitions:
        row = rows.get(transition.step_key)
        if row is None or not _apply_step_row(row, transition, graph, now):
            continue
        session.add(row)
        applied.append(transition)
        write_audit(
            session,
            actor="system",
            action="STEP_TRANSITION",
            object_type="step",
            object_id=f"{execution.id}:{transition.step_key}",
            detail={
                "from": transition.from_status.value,
                "to": transition.to_status.value,
                "reason_code": (
                    transition.reason_code.value
                    if transition.reason_code is not None
                    else None
                ),
                "source_event_id": source_event_id,
            },
            now=now,
        )

    state = state_from_rows(execution, list(rows.values()), graph)
    previous = ExecutionStatus(execution.status)
    derived = derive_execution_status(graph, state.steps, previous)
    status_changed = derived != previous
    if status_changed:
        execution.status = derived
        if derived in (ExecutionStatus.COMPLETED, ExecutionStatus.ABORTED):
            execution.finished_at = now
    execution.version += 1
    session.add(execution)

    for intent in alarms:
        category = AlarmCategory(intent.category)
        upsert_alarm(
            session,
            dedup_key=alarm_dedup_key(
                category=category,
                execution_id=execution.id,
                step_key=intent.step_key,
            ),
            category=category,
            severity=AlarmSeverity(intent.severity),
            reason_code=intent.reason_code,
            execution_id=execution.id,
            station_id=execution.station_id,
            camera_id=None,
            step_key=intent.step_key,
            source_event_id=intent.source_event_id,
            message=intent.message,
            now=now,
        )

    if applied:
        write_outbox(
            session,
            message_type=MessageType.STEP_UPDATED,
            station_id=execution.station_id,
            payload={
                "execution_id": execution.id,
                "steps": [transition.step_key for transition in applied],
            },
            now=now,
        )
    if status_changed or alarms:
        write_outbox(
            session,
            message_type=MessageType.EXECUTION_UPDATED,
            station_id=execution.station_id,
            payload={
                "execution_id": execution.id,
                "status": derived.value,
            },
            now=now,
        )
    session.flush()


def _validate_evidence(
    session: Session, row: StepExecution, evidence_ids: list[str]
) -> None:
    if not evidence_ids:
        return
    matched_ids = {str(event.get("event_id")) for event in row.matched_events}
    for evidence_id in evidence_ids:
        asset = session.get(EvidenceAsset, evidence_id)
        if asset is None or EvidenceStatus(asset.status) != EvidenceStatus.AVAILABLE:
            raise InvalidEvidence(evidence_id)
        linked = session.exec(
            select(EventEvidenceLink).where(
                col(EventEvidenceLink.evidence_id) == evidence_id
            )
        ).all()
        if not any(link.event_id in matched_ids for link in linked):
            raise InvalidEvidence(evidence_id)


def _review_fields(
    row: StepExecution,
    operator: str,
    reason: str,
    comment: str | None,
    now: datetime,
) -> None:
    row.reviewed_by = operator
    row.reviewed_at = now
    row.review_reason = reason
    row.review_comment = comment
    row.updated_at = now


def review_step(
    session: Session,
    *,
    execution_id: str,
    step_key: str,
    operator: str,
    decision: ReviewDecision,
    reason: str,
    comment: str | None,
    evidence_ids: list[str],
    now: datetime,
) -> ExecutionDetailRead:
    execution = _load_execution(session, execution_id)
    graph = load_graph(session, execution.sop_version_id)
    row = session.get(StepExecution, (execution_id, step_key))
    if row is None:
        raise StepNotFound(step_key)
    if _status_of(row) is not StepStatus.NEEDS_REVIEW:
        raise StepNotReviewable(step_key)
    if not operator.strip() or not reason.strip():
        raise StepNotReviewable("operator and reason are required")
    _validate_evidence(session, row, evidence_ids)

    target = (
        StepStatus.COMPLETED
        if decision is ReviewDecision.MARK_COMPLETED
        else StepStatus.FAILED
    )
    state = state_from_rows(execution, _step_rows(session, execution.id), graph)
    steps = dict(state.steps)
    steps[step_key] = dataclasses.replace(steps[step_key], status=target)
    reviewed_state = dataclasses.replace(state, steps=MappingProxyType(steps))
    activations = (
        activate_ready(graph, reviewed_state, now)
        if target is StepStatus.COMPLETED
        else []
    )
    transition = StepTransition(
        step_key=step_key,
        from_status=StepStatus.NEEDS_REVIEW,
        to_status=target,
        detail=f"review:{decision.value}",
    )
    apply_transitions(
        session,
        execution=execution,
        graph=graph,
        transitions=(transition, *activations),
        alarms=(),
        now=now,
    )

    reviewed = session.get(StepExecution, (execution_id, step_key))
    if reviewed is not None:
        reviewed.reason_code = None
        _review_fields(reviewed, operator, reason, comment, now)
        session.add(reviewed)
    write_audit(
        session,
        actor=operator,
        action="STEP_REVIEWED",
        object_type="step",
        object_id=f"{execution_id}:{step_key}",
        detail={
            "decision": decision.value,
            "reason": reason,
            "comment": comment,
            "evidence_ids": evidence_ids,
        },
        now=now,
    )
    session.flush()
    return get_execution(session, execution_id=execution_id, now=now)


def skip_step(
    session: Session,
    *,
    execution_id: str,
    step_key: str,
    operator: str,
    reason: str,
    comment: str | None,
    now: datetime,
) -> ExecutionDetailRead:
    execution = _load_execution(session, execution_id)
    graph = load_graph(session, execution.sop_version_id)
    compiled = graph.steps.get(step_key)
    if compiled is None:
        raise StepNotFound(step_key)
    if compiled.required:
        raise StepNotReviewable("step is required")
    row = session.get(StepExecution, (execution_id, step_key))
    if row is None:
        raise StepNotFound(step_key)
    current = _status_of(row)
    if current not in (StepStatus.PENDING, StepStatus.ACTIVE):
        raise StepNotReviewable(step_key)
    if not operator.strip() or not reason.strip():
        raise StepNotReviewable("operator and reason are required")

    state = state_from_rows(execution, _step_rows(session, execution.id), graph)
    steps = dict(state.steps)
    steps[step_key] = dataclasses.replace(
        steps[step_key],
        status=StepStatus.SKIPPED,
        reason_code=ReasonCode.MANUAL_SKIP,
        skipped_reason=reason,
    )
    skipped_state = dataclasses.replace(state, steps=MappingProxyType(steps))
    activations = activate_ready(graph, skipped_state, now)
    transition = StepTransition(
        step_key=step_key,
        from_status=current,
        to_status=StepStatus.SKIPPED,
        reason_code=ReasonCode.MANUAL_SKIP,
        detail=reason,
    )
    apply_transitions(
        session,
        execution=execution,
        graph=graph,
        transitions=(transition, *activations),
        alarms=(),
        now=now,
    )

    skipped = session.get(StepExecution, (execution_id, step_key))
    if skipped is not None:
        skipped.skipped_reason = reason
        _review_fields(skipped, operator, reason, comment, now)
        session.add(skipped)
    write_audit(
        session,
        actor=operator,
        action="STEP_SKIPPED",
        object_type="step",
        object_id=f"{execution_id}:{step_key}",
        detail={"reason": reason, "comment": comment},
        now=now,
    )
    session.flush()
    return get_execution(session, execution_id=execution_id, now=now)


def _step_actions(required: bool, status: StepStatus) -> list[str]:
    actions: list[str] = []
    if status is StepStatus.NEEDS_REVIEW:
        actions.append("REVIEW")
    if not required and status in (StepStatus.PENDING, StepStatus.ACTIVE):
        actions.append("SKIP")
    return actions


def _execution_actions(execution: SOPExecution) -> list[str]:
    status = ExecutionStatus(execution.status)
    actions: list[str] = []
    if status is ExecutionStatus.RUNNING:
        actions.append("PAUSE")
    if status is ExecutionStatus.PAUSED:
        actions.append("RESUME")
    if status in _ACTIVE_EXECUTION_STATUSES:
        actions.append("ABORT")
    return actions


def _evidence_for_events(session: Session, event_ids: list[str]) -> list[EvidenceRead]:
    if not event_ids:
        return []
    links = session.exec(
        select(EventEvidenceLink).where(col(EventEvidenceLink.event_id).in_(event_ids))
    ).all()
    assets: dict[str, EvidenceRead] = {}
    for link in links:
        asset = session.get(EvidenceAsset, link.evidence_id)
        if asset is None:
            continue
        assets[asset.id] = EvidenceRead(
            id=asset.id,
            event_id=asset.event_id,
            status=EvidenceStatus(asset.status),
            url=f"{settings.API_PREFIX}/evidence/{asset.id}",
            sha256=asset.sha256,
            width=asset.width,
            height=asset.height,
            created_at=asset.created_at,
        )
    return list(assets.values())


def get_execution(
    session: Session, *, execution_id: str, now: datetime
) -> ExecutionDetailRead:
    execution = _load_execution(session, execution_id)
    version = session.get(SOPVersion, execution.sop_version_id)
    if version is None:
        raise ExecutionNotFound(execution.sop_version_id)
    definition = session.get(SOPDefinition, version.sop_id)
    if definition is None:
        raise ExecutionNotFound(version.sop_id)
    rows = {row.step_key: row for row in _step_rows(session, execution.id)}

    steps: list[StepRead] = []
    for definition_row in ordered_step_definitions(session, version):
        row = rows.get(definition_row.step_key)
        if row is None:
            continue
        matched = [matched_from_json(event) for event in row.matched_events]
        steps.append(
            StepRead(
                key=definition_row.step_key,
                name=definition_row.name,
                type=StepType(definition_row.type),
                required=definition_row.required,
                status=_status_of(row),
                reason_code=(ReasonCode(row.reason_code) if row.reason_code else None),
                activated_at=row.activated_at,
                deadline_at=row.deadline_at,
                matched_events=[
                    MatchedEventRead(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        confidence=event.confidence,
                        occurred_at=event.occurred_at,
                        camera_id=event.camera_id,
                        camera_role=event.camera_role,
                        correlation_key=event.correlation_key,
                        accepted=event.accepted,
                    )
                    for event in matched
                ],
                evidence=_evidence_for_events(
                    session, [event.event_id for event in matched]
                ),
                skipped_reason=row.skipped_reason,
                review_reason=row.review_reason,
                review_comment=row.review_comment,
                reviewed_by=row.reviewed_by,
                reviewed_at=row.reviewed_at,
                allowed_actions=_step_actions(definition_row.required, _status_of(row)),
            )
        )
    return ExecutionDetailRead(
        id=execution.id,
        station_id=execution.station_id,
        sop_key=definition.key,
        sop_version=version.version,
        sop_content_hash=version.content_hash,
        status=ExecutionStatus(execution.status),
        workpiece_id=execution.workpiece_id,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        paused_at=execution.paused_at,
        total_paused_ms=execution.total_paused_ms,
        accept_events_until=execution.accept_events_until,
        steps=steps,
        allowed_actions=_execution_actions(execution),
        server_time=now,
    )


def list_executions(
    session: Session,
    *,
    station_id: str | None = None,
    status: ExecutionStatus | None = None,
) -> list[ExecutionSummaryRead]:
    statement = select(SOPExecution)
    if station_id is not None:
        statement = statement.where(SOPExecution.station_id == station_id)
    if status is not None:
        statement = statement.where(col(SOPExecution.status) == status.value)
    statement = statement.order_by(col(SOPExecution.started_at).desc())
    return [
        execution_summary_for(session, execution)[0]
        for execution in session.exec(statement).all()
    ]


def get_execution_timeline(
    session: Session, *, execution_id: str
) -> list[TimelineItemRead]:
    execution = _load_execution(session, execution_id)
    rows = _step_rows(session, execution_id)
    items: list[TimelineItemRead] = []
    for row in rows:
        status = _status_of(row)
        if status is StepStatus.PENDING:
            continue
        items.append(
            TimelineItemRead(
                type=TimelineItemType.STEP,
                at=row.updated_at,
                title=f"{row.step_key} · {status.value}",
                detail=row.skipped_reason,
                step_key=row.step_key,
                reason_code=(ReasonCode(row.reason_code) if row.reason_code else None),
                event_type=None,
                confidence=None,
                model=None,
            )
        )

    event_ids = sorted(
        {str(event.get("event_id")) for row in rows for event in row.matched_events}
    )
    if event_ids:
        events = session.exec(
            select(VisionEventRow).where(col(VisionEventRow.event_id).in_(event_ids))
        ).all()
        for event in events:
            model_name = event.model.get("name")
            model_version = event.model.get("version")
            items.append(
                TimelineItemRead(
                    type=TimelineItemType.EVENT,
                    at=event.occurred_at,
                    title=event.event_type,
                    detail=None,
                    step_key=None,
                    reason_code=None,
                    event_type=event.event_type,
                    confidence=event.confidence,
                    model=(
                        f"{model_name}@{model_version}"
                        if model_name is not None
                        else None
                    ),
                )
            )

    alarms = session.exec(select(Alarm).where(Alarm.execution_id == execution.id)).all()
    for alarm in alarms:
        items.append(
            TimelineItemRead(
                type=TimelineItemType.ALARM,
                at=alarm.first_seen_at,
                title=f"{alarm.category} · {alarm.severity}",
                detail=alarm.message,
                step_key=alarm.step_key,
                reason_code=(
                    ReasonCode(alarm.reason_code) if alarm.reason_code else None
                ),
                event_type=None,
                confidence=None,
                model=None,
            )
        )

    items.sort(key=lambda item: (item.at, _TIMELINE_ORDER[item.type]))
    return items
