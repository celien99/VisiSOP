from datetime import UTC, datetime

from contracts.enums import ProcessingResult
from contracts.events import VisionEvent
from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas.event import EventAssignRequest, EventIngestRead, EventRead
from app.application import event_service

router = APIRouter(prefix="/events", tags=["events"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=EventIngestRead, status_code=202, name="ingest_event")
def ingest_event(payload: VisionEvent, session: SessionDep) -> EventIngestRead:
    result = event_service.ingest_event(session, payload, _now())
    session.commit()
    return EventIngestRead.model_validate(result, from_attributes=True)


@router.get("", response_model=list[EventRead], name="list_events")
def list_events(
    session: SessionDep,
    result: ProcessingResult | None = None,
    station_id: str | None = None,
) -> list[EventRead]:
    return event_service.list_events(session, result=result, station_id=station_id)


@router.post(
    "/{event_id}/assign",
    response_model=EventIngestRead,
    name="assign_event",
)
def assign_event(
    event_id: str, payload: EventAssignRequest, session: SessionDep
) -> EventIngestRead:
    try:
        result = event_service.assign_event(
            session,
            event_id=event_id,
            execution_id=payload.execution_id,
            now=_now(),
        )
    except event_service.EventNotFound:
        raise HTTPException(status_code=404, detail="event not found") from None
    except event_service.NotQuarantined:
        raise HTTPException(
            status_code=409, detail="event is not quarantined"
        ) from None
    except event_service.AssignmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    session.commit()
    return EventIngestRead.model_validate(result, from_attributes=True)
