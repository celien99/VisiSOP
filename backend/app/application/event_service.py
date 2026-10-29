import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta

from contracts.catalog import InvalidAttributes, UnknownEventType, validate_attributes
from contracts.enums import ProcessingResult, ReasonCode
from contracts.events import RoutedSOPEvent, VisionEvent
from sqlmodel import Session, col, select

from app.api.schemas.event import EventRead
from app.application.audit import write_audit
from app.application.evidence_service import EvidenceService
from app.application.execution_service import apply_transitions
from app.application.graph_cache import load_graph
from app.application.state_codec import matched_to_json, state_from_rows
from app.core.config import settings
from app.domain.sop.engine import apply
from app.domain.sop.model import (
    AlarmIntent,
    EvidenceUpdate,
    ExecutionState,
    ExecutionStatus,
    SOPGraph,
    StepStatus,
    StepTransition,
    TransitionResult,
)
from app.infrastructure.evidence_store import EvidenceStore
from app.models import (
    EventEvidenceLink,
    EventProcessingReceipt,
    EvidenceAsset,
    EvidenceStatus,
    StationCameraBinding,
    StepExecution,
    VisionEventRow,
)
from app.models import (
    SOPExecution as SOPExecutionRow,
)

_ACTIVE_EXECUTION_STATUSES = (
    ExecutionStatus.RUNNING,
    ExecutionStatus.PAUSED,
    ExecutionStatus.NEEDS_REVIEW,
)
_EVENT_WINDOW_LEAD = timedelta(seconds=5)


@dataclass(frozen=True)
class Resolution:
    execution_id: str | None
    method: str
    candidate_ids: tuple[str, ...] = ()
    reason_code: ReasonCode | None = None


@dataclass(frozen=True)
class IngestResult:
    event_id: str
    result: ProcessingResult
    execution_id: str | None
    reason_code: ReasonCode | None
    detail: str | None
    received_at: datetime


class EventNotFound(LookupError):
    pass


class NotQuarantined(ValueError):
    pass


class AssignmentConflict(ValueError):
    pass


def _evidence_service() -> EvidenceService:
    return EvidenceService(EvidenceStore(settings.EVIDENCE_DIR))


def _camera_bound(
    session: Session, station_id: str, camera_id: str, at: datetime
) -> bool:
    statement = select(StationCameraBinding).where(
        col(StationCameraBinding.station_id) == station_id,
        col(StationCameraBinding.camera_id) == camera_id,
        col(StationCameraBinding.valid_from) <= at,
    )
    for binding in session.exec(statement).all():
        if binding.valid_to is None or at <= binding.valid_to:
            return True
    return False


def _in_window(execution: SOPExecutionRow, occurred_at: datetime) -> bool:
    return (
        execution.started_at - _EVENT_WINDOW_LEAD
        <= occurred_at
        <= execution.accept_events_until
    )


def _execution_reason(
    session: Session, execution: SOPExecutionRow, event: VisionEvent
) -> ReasonCode | None:
    if execution.station_id != event.station_id:
        return ReasonCode.CAMERA_CONFLICT
    if execution.status not in _ACTIVE_EXECUTION_STATUSES:
        return ReasonCode.LATE_EVENT
    if not _camera_bound(
        session, execution.station_id, event.camera_id, event.occurred_at
    ):
        return ReasonCode.CAMERA_CONFLICT
    if not _in_window(execution, event.occurred_at):
        return ReasonCode.LATE_EVENT
    return None


def _active_executions(session: Session, station_id: str) -> list[SOPExecutionRow]:
    statement = select(SOPExecutionRow).where(
        col(SOPExecutionRow.station_id) == station_id,
        col(SOPExecutionRow.status).in_(_ACTIVE_EXECUTION_STATUSES),
    )
    return list(session.exec(statement).all())


def resolve_execution(
    session: Session,
    event: VisionEvent,
    now: datetime,  # noqa: ARG001
) -> Resolution:
    if event.execution_id is not None:
        execution = session.get(SOPExecutionRow, event.execution_id)
        if execution is None:
            return Resolution(None, "EXPLICIT_UNKNOWN", ())
        reason = _execution_reason(session, execution, event)
        if reason is not None:
            return Resolution(None, "EXPLICIT", (execution.id,), reason)
        return Resolution(execution.id, "EXPLICIT")

    candidates = _active_executions(session, event.station_id)
    if not candidates:
        return Resolution(None, "NO_ACTIVE_EXECUTION")
    bound = [
        execution
        for execution in candidates
        if _camera_bound(
            session, execution.station_id, event.camera_id, event.occurred_at
        )
    ]
    if not bound:
        return Resolution(
            None,
            "CAMERA_UNBOUND",
            tuple(execution.id for execution in candidates),
            ReasonCode.CAMERA_CONFLICT,
        )
    in_window = [
        execution for execution in bound if _in_window(execution, event.occurred_at)
    ]
    if len(in_window) == 1:
        return Resolution(in_window[0].id, "ACTIVE_EXECUTION_WINDOW")
    if len(in_window) > 1:
        return Resolution(
            None,
            "AMBIGUOUS",
            tuple(execution.id for execution in in_window),
            ReasonCode.EXECUTION_AMBIGUOUS,
        )
    return Resolution(
        None,
        "OUTSIDE_WINDOW",
        tuple(execution.id for execution in bound),
        ReasonCode.LATE_EVENT,
    )


def _store_event(session: Session, event: VisionEvent) -> VisionEventRow:
    row = VisionEventRow(
        event_id=event.event_id,
        event_type=event.event_type,
        station_id=event.station_id,
        camera_id=event.camera_id,
        camera_role=event.camera_role,
        occurred_at=event.occurred_at,
        emitted_at=event.emitted_at,
        frame_seq=event.frame_seq,
        confidence=event.confidence,
        model=event.model.model_dump(),
        observation_ids=list(event.observation_ids),
        evidence_refs=list(event.evidence_refs),
        attributes=dict(event.attributes),
        correlation_key=event.correlation_key,
        execution_id=event.execution_id,
        raw=event.model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    return row


def _save_receipt(
    session: Session,
    event_id: str,
    result: ProcessingResult,
    *,
    execution_id: str | None,
    reason_code: ReasonCode | None,
    candidate_ids: tuple[str, ...],
    method: str,
    detail: str | None,
    rule_version: str | None = None,
    dsl_version: str | None = None,
    now: datetime,
) -> EventProcessingReceipt:
    receipt = session.get(EventProcessingReceipt, event_id)
    if receipt is None:
        receipt = EventProcessingReceipt(
            event_id=event_id,
            result=result,
            reason_code=reason_code,
            execution_id=execution_id,
            candidate_ids=list(candidate_ids),
            resolution_method=method,
            resolver_rule_version="1",
            rule_version=rule_version,
            dsl_version=dsl_version,
            detail=detail,
            processed_at=now,
        )
        session.add(receipt)
    else:
        receipt.result = result
        receipt.reason_code = reason_code
        receipt.execution_id = execution_id
        receipt.candidate_ids = list(candidate_ids)
        receipt.resolution_method = method
        receipt.rule_version = rule_version
        receipt.dsl_version = dsl_version
        receipt.detail = detail
        receipt.processed_at = now
        session.add(receipt)
    return receipt


def _result_from_receipt(
    receipt: EventProcessingReceipt, now: datetime, *, duplicate: bool
) -> IngestResult:
    return IngestResult(
        event_id=receipt.event_id,
        result=(
            ProcessingResult.DUPLICATE
            if duplicate
            else ProcessingResult(receipt.result)
        ),
        execution_id=receipt.execution_id,
        reason_code=(ReasonCode(receipt.reason_code) if receipt.reason_code else None),
        detail="duplicate delivery" if duplicate else receipt.detail,
        received_at=now,
    )


def _available_evidence(session: Session, row: StepExecution) -> bool:
    event_ids = [str(event.get("event_id")) for event in row.matched_events]
    if not event_ids:
        return False
    links = session.exec(
        select(EventEvidenceLink).where(col(EventEvidenceLink.event_id).in_(event_ids))
    ).all()
    for link in links:
        asset = session.get(EvidenceAsset, link.evidence_id)
        if (
            asset is not None
            and EvidenceStatus(asset.status) == EvidenceStatus.AVAILABLE
        ):
            return True
    return False


def _append_matched_events(
    session: Session,
    rows: dict[str, StepExecution],
    result: TransitionResult,
    now: datetime,
) -> None:
    for update in result.evidence_updates:
        row = rows.get(update.step_key)
        if row is None:
            continue
        if any(
            event.get("event_id") == update.event.event_id
            for event in row.matched_events
        ):
            continue
        row.matched_events = [
            *row.matched_events,
            matched_to_json(update.event),
        ]
        row.updated_at = now
        session.add(row)


def _evidence_policy(
    session: Session,
    graph: SOPGraph,
    rows: dict[str, StepExecution],
    result_transitions: tuple[StepTransition, ...],
    result_alarms: tuple[AlarmIntent, ...],
    event: VisionEvent,
) -> tuple[list[StepTransition], list[AlarmIntent]]:
    transitions = list(result_transitions)
    alarms = list(result_alarms)
    for index, transition in enumerate(transitions):
        if transition.to_status is not StepStatus.COMPLETED:
            continue
        compiled = graph.steps[transition.step_key]
        if compiled.evidence is None or not compiled.evidence.required:
            continue
        row = rows.get(transition.step_key)
        if row is not None and _available_evidence(session, row):
            continue
        transitions[index] = dataclasses.replace(
            transition,
            to_status=StepStatus.NEEDS_REVIEW,
            reason_code=ReasonCode.EVIDENCE_MISSING,
            detail="evidence_missing",
        )
        alarms.append(
            AlarmIntent(
                category="DATA_INTEGRITY",
                severity="HIGH",
                reason_code=ReasonCode.EVIDENCE_MISSING,
                step_key=transition.step_key,
                source_event_id=event.event_id,
                message=f"required evidence missing for {transition.step_key}",
            )
        )
    return transitions, alarms


def _out_of_order(
    state: ExecutionState,
    event: VisionEvent,
    transitions: tuple[StepTransition, ...],
    alarms: tuple[AlarmIntent, ...],
    evidence_updates: tuple[EvidenceUpdate, ...],
) -> AlarmIntent | None:
    if transitions or alarms or not evidence_updates:
        return None
    touched = {update.step_key for update in evidence_updates}
    live = {
        key
        for key, step in state.steps.items()
        if step.status in (StepStatus.ACTIVE, StepStatus.PENDING)
    }
    if touched & live:
        return None
    return AlarmIntent(
        category="PROCESS_COMPLIANCE",
        severity="MEDIUM",
        reason_code=ReasonCode.OUT_OF_ORDER,
        step_key=None,
        source_event_id=event.event_id,
        message=f"event {event.event_type} does not apply to an active step",
    )


def _apply_resolved(
    session: Session,
    event: VisionEvent,
    execution: SOPExecutionRow,
    resolution: Resolution,
    now: datetime,
) -> IngestResult:
    graph = load_graph(session, execution.sop_version_id)
    rows = {
        row.step_key: row
        for row in session.exec(
            select(StepExecution).where(StepExecution.execution_id == execution.id)
        ).all()
    }
    state = state_from_rows(execution, list(rows.values()), graph)
    payload = event.model_dump()
    payload["execution_id"] = execution.id
    routed = RoutedSOPEvent(
        **payload,
        resolution_method=resolution.method,
        resolved_at=now,
        resolver_rule_version="1",
        candidate_ids=resolution.candidate_ids,
        reason_code=resolution.reason_code,
    )
    result = apply(graph, state, routed, now)

    if result.processing_result is ProcessingResult.DUPLICATE:
        _save_receipt(
            session,
            event.event_id,
            ProcessingResult.DUPLICATE,
            execution_id=execution.id,
            reason_code=None,
            candidate_ids=resolution.candidate_ids,
            method=resolution.method,
            detail=result.detail,
            now=now,
        )
        session.flush()
        return IngestResult(
            event_id=event.event_id,
            result=ProcessingResult.DUPLICATE,
            execution_id=execution.id,
            reason_code=None,
            detail=result.detail,
            received_at=now,
        )

    _append_matched_events(session, rows, result, now)
    transitions, alarms = _evidence_policy(
        session,
        graph,
        rows,
        result.step_transitions,
        result.alarms,
        event,
    )
    out_of_order = _out_of_order(
        state,
        event,
        result.step_transitions,
        result.alarms,
        result.evidence_updates,
    )
    if out_of_order is not None:
        alarms.append(out_of_order)
    apply_transitions(
        session,
        execution=execution,
        graph=graph,
        transitions=tuple(transitions),
        alarms=tuple(alarms),
        now=now,
        source_event_id=event.event_id,
    )
    reason_code = result.reason_code
    if out_of_order is not None and reason_code is None:
        reason_code = ReasonCode.OUT_OF_ORDER
    _save_receipt(
        session,
        event.event_id,
        ProcessingResult.ACCEPTED,
        execution_id=execution.id,
        reason_code=reason_code,
        candidate_ids=resolution.candidate_ids,
        method=resolution.method,
        detail=result.detail,
        rule_version="1",
        dsl_version=str(graph.version),
        now=now,
    )
    session.flush()
    return IngestResult(
        event_id=event.event_id,
        result=ProcessingResult.ACCEPTED,
        execution_id=execution.id,
        reason_code=reason_code,
        detail=result.detail,
        received_at=now,
    )


def ingest_event(session: Session, event: VisionEvent, now: datetime) -> IngestResult:
    existing = session.get(EventProcessingReceipt, event.event_id)
    if existing is not None:
        return _result_from_receipt(existing, now, duplicate=True)

    try:
        validate_attributes(event.event_type, event.attributes)
    except (UnknownEventType, InvalidAttributes) as exc:
        _store_event(session, event)
        _save_receipt(
            session,
            event.event_id,
            ProcessingResult.REJECTED,
            execution_id=None,
            reason_code=ReasonCode.UNEXPECTED_STEP,
            candidate_ids=(),
            method="ATTRIBUTE_VALIDATION",
            detail=str(exc),
            now=now,
        )
        session.flush()
        return IngestResult(
            event_id=event.event_id,
            result=ProcessingResult.REJECTED,
            execution_id=None,
            reason_code=ReasonCode.UNEXPECTED_STEP,
            detail=str(exc),
            received_at=now,
        )

    resolution = resolve_execution(session, event, now)
    _store_event(session, event)
    _evidence_service().ingest_for_event(session, event, now)

    if resolution.execution_id is None:
        _save_receipt(
            session,
            event.event_id,
            ProcessingResult.QUARANTINED,
            execution_id=None,
            reason_code=resolution.reason_code,
            candidate_ids=resolution.candidate_ids,
            method=resolution.method,
            detail=resolution.method,
            now=now,
        )
        session.flush()
        return IngestResult(
            event_id=event.event_id,
            result=ProcessingResult.QUARANTINED,
            execution_id=None,
            reason_code=resolution.reason_code,
            detail=resolution.method,
            received_at=now,
        )

    execution = session.get(SOPExecutionRow, resolution.execution_id)
    if execution is None:  # pragma: no cover - resolution guarantees the row
        raise EventNotFound(resolution.execution_id)
    row = session.get(VisionEventRow, event.event_id)
    if row is not None:
        row.execution_id = execution.id
        session.add(row)
    return _apply_resolved(session, event, execution, resolution, now)


def assign_event(
    session: Session, *, event_id: str, execution_id: str, now: datetime
) -> IngestResult:
    receipt = session.get(EventProcessingReceipt, event_id)
    if receipt is None:
        raise EventNotFound(event_id)
    if ProcessingResult(receipt.result) is not ProcessingResult.QUARANTINED:
        raise NotQuarantined(event_id)
    row = session.get(VisionEventRow, event_id)
    if row is None:
        raise EventNotFound(event_id)
    event = VisionEvent.model_validate(row.raw)
    execution = session.get(SOPExecutionRow, execution_id)
    if execution is None:
        raise AssignmentConflict("execution not found")
    reason = _execution_reason(session, execution, event)
    if reason is not None:
        raise AssignmentConflict(reason.value)

    resolution = Resolution(execution.id, "EXPLICIT")
    row.execution_id = execution.id
    session.add(row)
    result = _apply_resolved(session, event, execution, resolution, now)
    write_audit(
        session,
        actor="system",
        action="event.assigned",
        object_type="event",
        object_id=event_id,
        detail={"execution_id": execution.id},
        now=now,
    )
    return result


def list_events(
    session: Session,
    *,
    result: ProcessingResult | None = None,
    station_id: str | None = None,
) -> list[EventRead]:
    statement = select(VisionEventRow, EventProcessingReceipt).join(
        EventProcessingReceipt,
        col(EventProcessingReceipt.event_id) == col(VisionEventRow.event_id),
    )
    if station_id is not None:
        statement = statement.where(VisionEventRow.station_id == station_id)
    if result is not None:
        statement = statement.where(col(EventProcessingReceipt.result) == result.value)
    statement = statement.order_by(col(VisionEventRow.occurred_at).desc())
    return [
        EventRead(
            event_id=event.event_id,
            event_type=event.event_type,
            station_id=event.station_id,
            camera_id=event.camera_id,
            occurred_at=event.occurred_at,
            result=ProcessingResult(receipt.result),
            reason_code=(
                ReasonCode(receipt.reason_code) if receipt.reason_code else None
            ),
            execution_id=receipt.execution_id,
            candidate_ids=list(receipt.candidate_ids),
            resolution_method=receipt.resolution_method,
            detail=receipt.detail,
        )
        for event, receipt in session.exec(statement).all()
    ]
