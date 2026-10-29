from datetime import UTC, datetime

from contracts.enums import AlarmCategory, AlarmStatus
from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas.alarm import AlarmActionRequest, AlarmRead
from app.application import alarm_service

router = APIRouter(prefix="/alarms", tags=["alarms"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[AlarmRead], name="list_alarms")
def list_alarms(
    session: SessionDep,
    status: AlarmStatus | None = None,
    category: AlarmCategory | None = None,
    station_id: str | None = None,
    execution_id: str | None = None,
) -> list[AlarmRead]:
    return alarm_service.list_alarms(
        session,
        status=status,
        category=category,
        station_id=station_id,
        execution_id=execution_id,
    )


@router.post(
    "/{alarm_id}/acknowledge", response_model=AlarmRead, name="acknowledge_alarm"
)
def acknowledge_alarm(
    alarm_id: str, payload: AlarmActionRequest, session: SessionDep
) -> AlarmRead:
    try:
        alarm = alarm_service.acknowledge_alarm(
            session,
            alarm_id=alarm_id,
            operator=payload.operator,
            comment=payload.comment,
            now=_now(),
        )
    except alarm_service.AlarmNotFound:
        raise HTTPException(status_code=404, detail="alarm not found") from None
    except alarm_service.AlarmConflict:
        raise HTTPException(status_code=409, detail="alarm is not open") from None
    session.commit()
    return alarm


@router.post("/{alarm_id}/resolve", response_model=AlarmRead, name="resolve_alarm")
def resolve_alarm(
    alarm_id: str, payload: AlarmActionRequest, session: SessionDep
) -> AlarmRead:
    try:
        alarm = alarm_service.resolve_alarm(
            session,
            alarm_id=alarm_id,
            operator=payload.operator,
            comment=payload.comment,
            now=_now(),
        )
    except alarm_service.AlarmNotFound:
        raise HTTPException(status_code=404, detail="alarm not found") from None
    except alarm_service.AlarmConflict:
        raise HTTPException(
            status_code=409, detail="alarm is already resolved"
        ) from None
    session.commit()
    return alarm
