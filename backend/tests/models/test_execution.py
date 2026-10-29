from datetime import datetime, timedelta

from sqlmodel import Session

from app.domain.sop.model import ExecutionStatus, StepStatus
from app.models import (
    SOPDefinition,
    SOPExecution,
    SOPVersion,
    Station,
    StepExecution,
)


def _seed_execution(db_session: Session, now: datetime) -> SOPExecution:
    db_session.add(
        Station(id="st-01", code="ST-01", name="演示工位", zone="A", created_at=now)
    )
    db_session.add(SOPDefinition(id="sop-1", key="k", name="K", created_at=now))
    db_session.add(
        SOPVersion(
            id="v1",
            sop_id="sop-1",
            version=1,
            status="DRAFT",
            dsl={},
            dsl_schema_version="1.0",
            content_hash="h",
            created_at=now,
        )
    )
    db_session.commit()
    execution = SOPExecution(
        id="e1",
        station_id="st-01",
        sop_version_id="v1",
        status=ExecutionStatus.RUNNING,
        started_at=now,
        accept_events_until=now + timedelta(minutes=10),
        created_at=now,
    )
    db_session.add(execution)
    db_session.commit()
    return execution


def test_step_rows_use_composite_key_and_round_trip_matched_events(
    db_session: Session, now: datetime
) -> None:
    _seed_execution(db_session, now)
    db_session.add(
        StepExecution(
            execution_id="e1",
            step_key="pick_bottle",
            status=StepStatus.ACTIVE,
            activated_at=now,
            matched_events=[{"event_id": "evt-1", "confidence": 0.9}],
            updated_at=now,
        )
    )
    db_session.commit()

    stored = db_session.get(StepExecution, ("e1", "pick_bottle"))
    assert stored is not None
    # SQLModel reads enum columns back as their string values; use == here.
    assert stored.status == StepStatus.ACTIVE
    assert stored.matched_events == [{"event_id": "evt-1", "confidence": 0.9}]
    assert db_session.get(SOPExecution, "e1").version == 1  # type: ignore[union-attr]
