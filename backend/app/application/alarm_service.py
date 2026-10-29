from datetime import datetime
from uuid import uuid4

from contracts.enums import AlarmCategory, AlarmSeverity, AlarmStatus, ReasonCode
from sqlmodel import Session, col, select

from app.models import Alarm

_OPEN_STATUSES = (AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED)


def alarm_dedup_key(
    *,
    category: AlarmCategory,
    execution_id: str | None = None,
    station_id: str | None = None,
    camera_id: str | None = None,
    step_key: str | None = None,
) -> str:
    if execution_id is not None:
        return f"execution:{execution_id}:step:{step_key or '-'}:{category.value}"
    if station_id is None:
        raise ValueError("station_id is required for station-level alarms")
    return f"station:{station_id}:camera:{camera_id or '-'}:{category.value}"


def upsert_alarm(
    session: Session,
    *,
    dedup_key: str,
    category: AlarmCategory,
    severity: AlarmSeverity,
    reason_code: ReasonCode | None,
    execution_id: str | None,
    station_id: str,
    camera_id: str | None,
    step_key: str | None,
    source_event_id: str | None,
    message: str,
    now: datetime,
) -> Alarm:
    statement = select(Alarm).where(
        Alarm.dedup_key == dedup_key, col(Alarm.status).in_(_OPEN_STATUSES)
    )
    existing = session.exec(statement).first()
    if existing is not None:
        existing.last_seen_at = now
        existing.occurrence_count += 1
        existing.severity = severity
        existing.reason_code = reason_code
        existing.source_event_id = source_event_id
        existing.message = message
        session.add(existing)
        return existing

    alarm = Alarm(
        id=str(uuid4()),
        dedup_key=dedup_key,
        category=category,
        severity=severity,
        status=AlarmStatus.OPEN,
        reason_code=reason_code,
        execution_id=execution_id,
        station_id=station_id,
        camera_id=camera_id,
        step_key=step_key,
        source_event_id=source_event_id,
        message=message,
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=1,
    )
    session.add(alarm)
    return alarm
