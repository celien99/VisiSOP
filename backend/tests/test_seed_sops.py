from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.core.config import settings
from app.models import Camera, SOPDefinition, SOPExecution
from app.scripts.seed_sops import seed_sops


def test_seed_is_idempotent(db_session: Session, now: datetime) -> None:
    first = seed_sops(db_session, now)
    second = seed_sops(db_session, now)
    assert first.sop_key == second.sop_key == "bottle_transfer"
    assert first.station_id == second.station_id == "st-01"
    assert first.camera_id == second.camera_id == "cam-01"
    assert first.sop_version_id == second.sop_version_id
    assert first.created_execution is True
    assert second.created_execution is False
    assert db_session.exec(select(func.count()).select_from(SOPDefinition)).one() == 2


def test_seed_leaves_preview_urls_to_the_runtime_registration(
    db_session: Session, now: datetime
) -> None:
    seed_sops(db_session, now)

    camera = db_session.get(Camera, "cam-01")

    assert camera is not None
    assert camera.source_type == "mvs"
    assert camera.preview_url is None
    assert camera.snapshot_url is None


def test_seed_publishes_both_sops_and_activates_the_requested_one(
    db_session: Session, now: datetime
) -> None:
    result = seed_sops(db_session, now, active_sop="remote_battery")

    keys = {definition.key for definition in db_session.exec(select(SOPDefinition))}
    assert keys == {"bottle_transfer", "remote_battery"}
    assert result.sop_key == "remote_battery"
    execution = db_session.get(SOPExecution, result.execution_id)
    assert execution is not None
    assert execution.sop_version_id == result.sop_version_id


def test_switching_the_active_sop_aborts_the_previous_execution(
    db_session: Session, now: datetime
) -> None:
    first = seed_sops(db_session, now)
    second = seed_sops(db_session, now, active_sop="remote_battery")

    db_session.expire_all()
    assert first.execution_id != second.execution_id
    previous = db_session.get(SOPExecution, first.execution_id)
    current = db_session.get(SOPExecution, second.execution_id)
    assert previous is not None and previous.status == "ABORTED"
    assert current is not None and current.status == "RUNNING"


def test_seed_replaces_an_execution_past_its_accept_window(
    db_session: Session, now: datetime
) -> None:
    first = seed_sops(db_session, now)
    later = now + timedelta(milliseconds=settings.EXECUTION_ACCEPT_WINDOW_MS + 1000)

    second = seed_sops(db_session, later)

    assert second.created_execution is True
    assert second.execution_id != first.execution_id
    db_session.expire_all()
    previous = db_session.get(SOPExecution, first.execution_id)
    current = db_session.get(SOPExecution, second.execution_id)
    assert previous is not None and previous.status == "ABORTED"
    assert current is not None and current.status == "RUNNING"
