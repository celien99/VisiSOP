from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas.execution import (
    ExecutionAbortRequest,
    ExecutionCreate,
    ExecutionDetailRead,
    ExecutionSummaryRead,
    StepReviewRequest,
    StepSkipRequest,
    TimelineItemRead,
)
from app.application import execution_service, station_service
from app.domain.sop.model import ExecutionStatus

router = APIRouter(tags=["executions"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.post(
    "/stations/{station_id}/executions",
    response_model=ExecutionDetailRead,
    status_code=201,
    name="create_execution",
)
def create_execution(
    station_id: str, payload: ExecutionCreate, session: SessionDep
) -> ExecutionDetailRead:
    try:
        detail = execution_service.create_execution(
            session,
            station_id=station_id,
            sop_version_id=payload.sop_version_id,
            workpiece_id=payload.workpiece_id,
            now=_now(),
        )
    except station_service.StationNotFound:
        raise HTTPException(status_code=404, detail="station not found") from None
    except execution_service.SopVersionNotFound:
        raise HTTPException(status_code=404, detail="SOP version not found") from None
    except execution_service.SopNotPublished:
        raise HTTPException(
            status_code=422, detail="SOP version is not published"
        ) from None
    except execution_service.ExecutionConflict:
        raise HTTPException(
            status_code=409, detail="station already has an active execution"
        ) from None
    session.commit()
    return detail


@router.get(
    "/executions", response_model=list[ExecutionSummaryRead], name="list_executions"
)
def list_executions(
    session: SessionDep,
    station_id: str | None = None,
    status: ExecutionStatus | None = None,
) -> list[ExecutionSummaryRead]:
    return execution_service.list_executions(
        session, station_id=station_id, status=status
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionDetailRead,
    name="get_execution",
)
def get_execution(execution_id: str, session: SessionDep) -> ExecutionDetailRead:
    try:
        return execution_service.get_execution(
            session, execution_id=execution_id, now=_now()
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None


@router.post(
    "/executions/{execution_id}/pause",
    response_model=ExecutionDetailRead,
    name="pause_execution",
)
def pause_execution(execution_id: str, session: SessionDep) -> ExecutionDetailRead:
    try:
        detail = execution_service.pause_execution(
            session, execution_id=execution_id, now=_now()
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None
    except execution_service.ExecutionConflict:
        raise HTTPException(
            status_code=409, detail="execution is not running"
        ) from None
    session.commit()
    return detail


@router.post(
    "/executions/{execution_id}/resume",
    response_model=ExecutionDetailRead,
    name="resume_execution",
)
def resume_execution(execution_id: str, session: SessionDep) -> ExecutionDetailRead:
    try:
        detail = execution_service.resume_execution(
            session, execution_id=execution_id, now=_now()
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None
    except execution_service.ExecutionConflict:
        raise HTTPException(status_code=409, detail="execution is not paused") from None
    session.commit()
    return detail


@router.post(
    "/executions/{execution_id}/abort",
    response_model=ExecutionDetailRead,
    name="abort_execution",
)
def abort_execution(
    execution_id: str, payload: ExecutionAbortRequest, session: SessionDep
) -> ExecutionDetailRead:
    try:
        detail = execution_service.abort_execution(
            session, execution_id=execution_id, reason=payload.reason, now=_now()
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None
    except execution_service.ExecutionConflict:
        raise HTTPException(status_code=409, detail="execution is not active") from None
    session.commit()
    return detail


@router.get(
    "/executions/{execution_id}/timeline",
    response_model=list[TimelineItemRead],
    name="get_execution_timeline",
)
def get_execution_timeline(
    execution_id: str, session: SessionDep
) -> list[TimelineItemRead]:
    try:
        return execution_service.get_execution_timeline(
            session, execution_id=execution_id
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None


@router.post(
    "/executions/{execution_id}/steps/{step_key}/review",
    response_model=ExecutionDetailRead,
    name="review_step",
)
def review_step(
    execution_id: str,
    step_key: str,
    payload: StepReviewRequest,
    session: SessionDep,
) -> ExecutionDetailRead:
    try:
        detail = execution_service.review_step(
            session,
            execution_id=execution_id,
            step_key=step_key,
            operator=payload.operator,
            decision=payload.decision,
            reason=payload.reason,
            comment=payload.comment,
            evidence_ids=payload.evidence_ids,
            now=_now(),
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None
    except execution_service.StepNotFound:
        raise HTTPException(status_code=404, detail="step not found") from None
    except execution_service.StepNotReviewable:
        raise HTTPException(
            status_code=409, detail="step is not awaiting review"
        ) from None
    except execution_service.InvalidEvidence:
        raise HTTPException(status_code=422, detail="evidence is not usable") from None
    session.commit()
    return detail


@router.post(
    "/executions/{execution_id}/steps/{step_key}/skip",
    response_model=ExecutionDetailRead,
    name="skip_step",
)
def skip_step(
    execution_id: str,
    step_key: str,
    payload: StepSkipRequest,
    session: SessionDep,
) -> ExecutionDetailRead:
    try:
        detail = execution_service.skip_step(
            session,
            execution_id=execution_id,
            step_key=step_key,
            operator=payload.operator,
            reason=payload.reason,
            comment=payload.comment,
            now=_now(),
        )
    except execution_service.ExecutionNotFound:
        raise HTTPException(status_code=404, detail="execution not found") from None
    except execution_service.StepNotFound:
        raise HTTPException(status_code=404, detail="step not found") from None
    except execution_service.StepNotReviewable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    session.commit()
    return detail
