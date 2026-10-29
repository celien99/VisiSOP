from datetime import datetime, timedelta

from sqlmodel import Session, func, select

from app.application.event_service import ingest_event
from app.api.schemas.execution import ExecutionDetailRead
from app.models import Alarm, EventEvidenceLink, SOPExecution, StepExecution
from contracts.enums import ProcessingResult


def test_duplicate_delivery_is_idempotent(
    db_session: Session,
    active_execution: ExecutionDetailRead,
    event_with_evidence,
    now: datetime,
) -> None:
    first = ingest_event(db_session, event_with_evidence, now)
    second = ingest_event(db_session, event_with_evidence, now)
    assert first.result is ProcessingResult.ACCEPTED
    assert second.result is ProcessingResult.DUPLICATE
    pick = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert pick is not None
    assert len(pick.matched_events) == 1
    links = db_session.exec(
        select(func.count()).select_from(EventEvidenceLink)
    ).one()
    assert links == 1


def test_missing_evidence_forces_review(
    db_session: Session,
    active_execution: ExecutionDetailRead,
    make_zone_event,
    now: datetime,
) -> None:
    first = ingest_event(
        db_session, make_zone_event("evt-a", "pickup", now, evidence=False), now
    )
    second = ingest_event(
        db_session,
        make_zone_event(
            "evt-b", "pickup", now + timedelta(milliseconds=600), evidence=False
        ),
        now + timedelta(milliseconds=600),
    )
    assert first.result is ProcessingResult.ACCEPTED
    assert second.result is ProcessingResult.ACCEPTED
    pick = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert pick is not None
    assert pick.status == "NEEDS_REVIEW"
    assert pick.reason_code == "EVIDENCE_MISSING"
    execution = db_session.get(SOPExecution, active_execution.id)
    assert execution is not None
    assert execution.status == "NEEDS_REVIEW"


def test_late_pickup_does_not_complete_the_target_step(
    db_session: Session,
    active_execution: ExecutionDetailRead,
    make_zone_event,
    now: datetime,
) -> None:
    ingest_event(db_session, make_zone_event("evt-p1", "pickup", now), now)
    ingest_event(
        db_session,
        make_zone_event("evt-p2", "pickup", now + timedelta(milliseconds=600)),
        now + timedelta(milliseconds=600),
    )
    result = ingest_event(
        db_session,
        make_zone_event("evt-p3", "pickup", now + timedelta(milliseconds=1200)),
        now + timedelta(milliseconds=1200),
    )
    assert result.result is ProcessingResult.ACCEPTED
    place = db_session.get(StepExecution, (active_execution.id, "place_bottle"))
    assert place is not None
    assert place.status == "ACTIVE"
    alarms = db_session.exec(select(Alarm)).all()
    assert any(alarm.reason_code == "OUT_OF_ORDER" for alarm in alarms)
