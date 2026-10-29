from datetime import datetime
from uuid import uuid4

from contracts.enums import (
    AlarmCategory,
    AlarmSeverity,
    AlarmStatus,
    MessageType,
    ReasonCode,
)
from sqlmodel import Session, col, select

from app.api.schemas.alarm import AlarmRead
from app.application.audit import write_audit
from app.application.outbox import write_outbox
from app.models import Alarm

_OPEN_STATUSES = (AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED)


class AlarmNotFound(LookupError):
    pass


class AlarmConflict(ValueError):
    pass


def alarm_read(alarm: Alarm) -> AlarmRead:
    return AlarmRead(
        id=alarm.id,
        execution_id=alarm.execution_id,
        station_id=alarm.station_id,
        camera_id=alarm.camera_id,
        category=alarm.category,
        severity=alarm.severity,
        status=alarm.status,
        reason_code=alarm.reason_code,
        step_key=alarm.step_key,
        message=alarm.message,
        first_seen_at=alarm.first_seen_at,
        last_seen_at=alarm.last_seen_at,
        occurrence_count=alarm.occurrence_count,
        acknowledged_at=alarm.acknowledged_at,
        acknowledged_by=alarm.acknowledged_by,
        resolved_at=alarm.resolved_at,
        resolved_by=alarm.resolved_by,
        comment=alarm.comment,
    )


def list_alarms(
    session: Session,
    *,
    status: AlarmStatus | None = None,
    category: AlarmCategory | None = None,
    station_id: str | None = None,
    execution_id: str | None = None,
) -> list[AlarmRead]:
    statement = select(Alarm)
    if status is not None:
        statement = statement.where(col(Alarm.status) == status.value)
    if category is not None:
        statement = statement.where(col(Alarm.category) == category.value)
    if station_id is not None:
        statement = statement.where(col(Alarm.station_id) == station_id)
    if execution_id is not None:
        statement = statement.where(col(Alarm.execution_id) == execution_id)
    statement = statement.order_by(col(Alarm.first_seen_at).desc())
    return [alarm_read(alarm) for alarm in session.exec(statement).all()]


def _load(session: Session, alarm_id: str) -> Alarm:
    alarm = session.get(Alarm, alarm_id)
    if alarm is None:
        raise AlarmNotFound(alarm_id)
    return alarm


def acknowledge_alarm(
    session: Session,
    *,
    alarm_id: str,
    operator: str,
    comment: str | None,
    now: datetime,
) -> AlarmRead:
    alarm = _load(session, alarm_id)
    if AlarmStatus(alarm.status) is not AlarmStatus.OPEN:
        raise AlarmConflict(alarm_id)
    alarm.status = AlarmStatus.ACKNOWLEDGED
    alarm.acknowledged_at = now
    alarm.acknowledged_by = operator
    if comment is not None:
        alarm.comment = comment
    session.add(alarm)
    write_audit(
        session,
        actor=operator,
        action="alarm.acknowledged",
        object_type="alarm",
        object_id=alarm.id,
        detail={"comment": comment},
        now=now,
    )
    write_outbox(
        session,
        message_type=MessageType.ALARM_UPDATED,
        station_id=alarm.station_id,
        payload={"alarm_id": alarm.id, "status": AlarmStatus.ACKNOWLEDGED.value},
        now=now,
    )
    return alarm_read(alarm)


def resolve_alarm(
    session: Session,
    *,
    alarm_id: str,
    operator: str,
    comment: str | None,
    now: datetime,
) -> AlarmRead:
    alarm = _load(session, alarm_id)
    if AlarmStatus(alarm.status) not in _OPEN_STATUSES:
        raise AlarmConflict(alarm_id)
    alarm.status = AlarmStatus.RESOLVED
    alarm.resolved_at = now
    alarm.resolved_by = operator
    if comment is not None:
        alarm.comment = comment
    session.add(alarm)
    write_audit(
        session,
        actor=operator,
        action="alarm.resolved",
        object_type="alarm",
        object_id=alarm.id,
        detail={"comment": comment},
        now=now,
    )
    write_outbox(
        session,
        message_type=MessageType.ALARM_UPDATED,
        station_id=alarm.station_id,
        payload={"alarm_id": alarm.id, "status": AlarmStatus.RESOLVED.value},
        now=now,
    )
    return alarm_read(alarm)


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
