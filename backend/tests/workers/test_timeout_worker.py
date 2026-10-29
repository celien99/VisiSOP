from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.api.schemas.execution import ExecutionDetailRead
from app.application.event_service import ingest_event
from app.models import Alarm, SOPExecution, StepExecution
from app.workers.timeout_worker import process_timeouts


def test_expired_active_step_times_out_once(
    db_session: Session, active_execution: ExecutionDetailRead, now: datetime
) -> None:
    step = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert step is not None
    step.deadline_at = now - timedelta(seconds=1)
    db_session.add(step)
    db_session.commit()

    assert process_timeouts(db_session, now) == 1
    db_session.expire_all()
    timed_out_step = db_session.get(
        StepExecution, (active_execution.id, "pick_bottle")
    )
    assert timed_out_step is not None
    assert timed_out_step.status == "TIMED_OUT"
    execution = db_session.get(SOPExecution, active_execution.id)
    assert execution is not None
    assert execution.status == "NEEDS_REVIEW"
    assert process_timeouts(db_session, now) == 0


def test_paused_execution_never_times_out(
    db_session: Session, active_execution: ExecutionDetailRead, now: datetime
) -> None:
    execution = db_session.get(SOPExecution, active_execution.id)
    assert execution is not None
    execution.status = "PAUSED"  # type: ignore[assignment]
    step = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert step is not None
    step.deadline_at = now - timedelta(seconds=1)
    db_session.add(execution)
    db_session.add(step)
    db_session.commit()

    assert process_timeouts(db_session, now) == 0


def test_low_confidence_timeout_needs_review(
    db_session: Session,
    active_execution: ExecutionDetailRead,
    make_zone_event,
    now: datetime,
) -> None:
    event = make_zone_event("evt-low", "pickup", now).model_copy(
        update={"confidence": 0.1}
    )
    ingest_event(db_session, event, now)

    step = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert step is not None
    step.deadline_at = now - timedelta(seconds=1)
    db_session.add(step)
    db_session.commit()

    assert process_timeouts(db_session, now) == 1
    db_session.expire_all()
    timed_out_step = db_session.get(
        StepExecution, (active_execution.id, "pick_bottle")
    )
    assert timed_out_step is not None
    assert timed_out_step.status == "NEEDS_REVIEW"
    assert timed_out_step.reason_code == "LOW_CONFIDENCE"
    alarms = db_session.exec(select(Alarm)).all()
    assert any(alarm.category == "VISION_QUALITY" for alarm in alarms)
