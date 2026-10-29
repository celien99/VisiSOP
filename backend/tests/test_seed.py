from datetime import datetime

from sqlmodel import Session, func, select

from app.models import SOPDefinition
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
