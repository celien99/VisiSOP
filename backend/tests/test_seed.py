from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.core.config import settings
from app.models import SOPDefinition, SOPExecution
from app.scripts.seed_demo import seed_demo


def test_seed_is_idempotent(db_session: Session, now: datetime) -> None:
    first = seed_demo(db_session, now)
    second = seed_demo(db_session, now)
    assert first.station_id == second.station_id == "st-01"
    assert first.camera_id == second.camera_id == "cam-01"
    assert first.sop_version_id == second.sop_version_id
    assert first.created_execution is True
    assert second.created_execution is False
    assert (
        db_session.exec(select(func.count()).select_from(SOPDefinition)).one() == 1
    )


def test_seed_replaces_an_execution_past_its_accept_window(
    db_session: Session, now: datetime
) -> None:
    first = seed_demo(db_session, now)
    later = now + timedelta(milliseconds=settings.EXECUTION_ACCEPT_WINDOW_MS + 1000)

    second = seed_demo(db_session, later)

    assert second.created_execution is True
    assert second.execution_id != first.execution_id
    db_session.expire_all()
    assert db_session.get(SOPExecution, first.execution_id).status == "ABORTED"
    assert db_session.get(SOPExecution, second.execution_id).status == "RUNNING"
