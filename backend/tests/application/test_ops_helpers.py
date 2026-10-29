from datetime import datetime

from sqlmodel import Session, select

from app.application.alarm_service import upsert_alarm
from app.application.audit import write_audit
from app.application.outbox import write_outbox
from app.models import Alarm, AuditRecord, OutboxMessage
from contracts.enums import AlarmCategory, AlarmSeverity, AlarmStatus, MessageType


def test_alarm_dedup_updates_open_row(db_session: Session, now: datetime) -> None:
    kw = {
        "dedup_key": "execution:e1:step:a:PROCESS_COMPLIANCE",
        "category": AlarmCategory.PROCESS_COMPLIANCE,
        "severity": AlarmSeverity.HIGH,
        "reason_code": "TIMEOUT",
        "execution_id": "e1",
        "station_id": "st-01",
        "camera_id": None,
        "step_key": "a",
        "source_event_id": None,
        "message": "step timed out",
        "now": now,
    }
    first = upsert_alarm(db_session, **kw)  # type: ignore[arg-type]
    second = upsert_alarm(db_session, **kw)  # type: ignore[arg-type]
    db_session.commit()
    assert first.id == second.id
    stored = db_session.get(Alarm, first.id)
    assert stored is not None
    assert stored.occurrence_count == 2


def test_resolved_alarm_does_not_absorb_new_occurrences(
    db_session: Session, now: datetime
) -> None:
    kw = {
        "dedup_key": "station:st-01:camera:-:DEVICE_HEALTH",
        "category": AlarmCategory.DEVICE_HEALTH,
        "severity": AlarmSeverity.HIGH,
        "reason_code": None,
        "execution_id": None,
        "station_id": "st-01",
        "camera_id": None,
        "step_key": None,
        "source_event_id": None,
        "message": "runtime unavailable",
        "now": now,
    }
    first = upsert_alarm(db_session, **kw)  # type: ignore[arg-type]
    first.status = AlarmStatus.RESOLVED
    db_session.add(first)
    db_session.commit()

    second = upsert_alarm(db_session, **kw)  # type: ignore[arg-type]
    db_session.commit()
    assert second.id != first.id


def test_audit_and_outbox_are_rows_in_the_callers_transaction(
    db_session: Session, now: datetime
) -> None:
    write_audit(
        db_session,
        actor="tester",
        action="test",
        object_type="step",
        object_id="a",
        detail={"x": 1},
        now=now,
    )
    msg = write_outbox(
        db_session,
        message_type=MessageType.STEP_UPDATED,
        station_id="st-01",
        payload={"execution_id": "e1"},
        now=now,
    )
    db_session.commit()
    record = db_session.exec(select(AuditRecord)).one()
    assert record.action == "test"
    stored = db_session.get(OutboxMessage, msg.id)
    assert stored is not None
    assert stored.dispatched_at is None
