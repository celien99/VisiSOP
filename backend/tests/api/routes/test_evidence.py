from datetime import datetime
from pathlib import Path

from contracts.events import ModelRef, VisionEvent
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session

from app.application.evidence_service import EvidenceService
from app.infrastructure.evidence_store import EvidenceStore
from app.models import VisionEventRow


def _event(event_id: str, refs: list[str], now: datetime) -> VisionEvent:
    return VisionEvent(
        schema_version="1.0",
        event_id=event_id,
        event_type="bottle_in_pickup_zone",
        station_id="st-01",
        camera_id="cam-01",
        occurred_at=now,
        emitted_at=now,
        frame_seq=1,
        confidence=0.9,
        model=ModelRef(name="demo", version="1"),
        attributes={"object_class": "bottle", "zone": "pickup", "bbox": [0, 0, 1, 1]},
        evidence_refs=tuple(refs),
    )


def _insert_event(session: Session, event: VisionEvent) -> None:
    session.add(
        VisionEventRow(
            event_id=event.event_id,
            event_type=event.event_type,
            station_id=event.station_id,
            camera_id=event.camera_id,
            camera_role=event.camera_role,
            occurred_at=event.occurred_at,
            emitted_at=event.emitted_at,
            frame_seq=event.frame_seq,
            confidence=event.confidence,
            model=event.model.model_dump(),
            observation_ids=list(event.observation_ids),
            evidence_refs=list(event.evidence_refs),
            attributes=dict(event.attributes),
            correlation_key=event.correlation_key,
            execution_id=event.execution_id,
            raw=event.model_dump(mode="json"),
        )
    )
    session.flush()


def test_available_evidence_is_served(
    client: TestClient, db_session: Session, evidence_dir: Path, now: datetime
) -> None:
    (evidence_dir / "tmp").mkdir()
    Image.new("RGB", (20, 10), "white").save(
        evidence_dir / "tmp" / "evt-1.jpg", "JPEG"
    )
    event = _event("evt-1", ["tmp/evt-1.jpg"], now)
    _insert_event(db_session, event)
    [asset] = EvidenceService(EvidenceStore(evidence_dir)).ingest_for_event(
        db_session, event, now
    )
    db_session.commit()

    response = client.get(f"/api/evidence/{asset.id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


def test_unavailable_evidence_is_404(
    client: TestClient, db_session: Session, evidence_dir: Path, now: datetime
) -> None:
    event = _event("evt-2", ["tmp/evt-2.jpg"], now)
    _insert_event(db_session, event)
    [asset] = EvidenceService(EvidenceStore(evidence_dir)).ingest_for_event(
        db_session, event, now
    )
    db_session.commit()

    response = client.get(f"/api/evidence/{asset.id}")
    assert response.status_code == 404
    assert "MISSING" in response.json()["detail"]
