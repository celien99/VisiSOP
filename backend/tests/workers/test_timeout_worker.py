from datetime import datetime, timedelta

from sqlmodel import Session

from app.api.schemas.execution import ExecutionDetailRead
from app.models import SOPExecution, StepExecution
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
