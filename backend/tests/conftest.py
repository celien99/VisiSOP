import json
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from contracts.events import ModelRef, VisionEvent
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.execution import ExecutionDetailRead
from app.application import execution_service
from app.application.alarm_service import upsert_alarm
from app.application.runtime_registry import runtime_registry
from app.application.sop_service import create_sop, publish_sop
from app.core.config import settings
from app.core.db import engine
from app.main import app
from app.models import (
    Alarm,
    Camera,
    SOPVersion,
    Station,
    StationCameraBinding,
)
from contracts.enums import AlarmCategory, AlarmSeverity, CameraRole

DEMO_SOP_PATH = Path(__file__).parents[1] / "app" / "seed" / "bottle_transfer.json"


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_runtime_registry() -> Generator[None]:
    runtime_registry.clear()
    yield
    runtime_registry.clear()


@pytest.fixture
def db_connection() -> Generator[Connection]:
    # shortcut: tests share one connection/session; upgrade to a per-test database
    # when parallel tests arrive.
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def db_session(db_connection: Connection) -> Generator[Session]:
    with Session(
        bind=db_connection, join_transaction_mode="create_savepoint"
    ) as session:
        yield session


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    # no `with`: lifespan/workers are not started
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def evidence_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(settings, "EVIDENCE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def seeded_station(db_session: Session, now: datetime) -> Station:
    station = Station(
        id="st-01", code="ST-01", name="演示工位", zone="A", created_at=now
    )
    camera = Camera(
        id="cam-01",
        code="CAM-01",
        name="主相机",
        runtime_id="runtime-01",
        source_type="gige",
        source_config={"serial": "demo"},
        preview_url="http://127.0.0.1:8001/stream/cam-01",
        snapshot_url="http://127.0.0.1:8001/snapshot/cam-01",
        created_at=now,
    )
    db_session.add(station)
    db_session.add(camera)
    db_session.commit()
    db_session.add(
        StationCameraBinding(
            id="bind-01",
            station_id="st-01",
            camera_id="cam-01",
            role=CameraRole.OVERVIEW,
            valid_from=now,
        )
    )
    db_session.commit()
    return station


@pytest.fixture
def published_sop(db_session: Session, now: datetime) -> SOPVersion:
    dsl = json.loads(DEMO_SOP_PATH.read_text(encoding="utf-8"))
    version = create_sop(
        db_session, key="bottle_transfer", name="瓶体转移演示", dsl=dsl, now=now
    )
    publish_sop(db_session, sop_id=version.sop_id, now=now)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(SOPVersion, version.id)
    assert stored is not None
    return stored


@pytest.fixture
def active_execution(
    db_session: Session,
    published_sop: SOPVersion,
    seeded_station: Station,
    now: datetime,
) -> ExecutionDetailRead:
    # Created at the fixture clock so ingestion tests can post events deterministically.
    detail = execution_service.create_execution(
        db_session,
        station_id="st-01",
        sop_version_id=published_sop.id,
        workpiece_id=None,
        now=now,
    )
    db_session.commit()
    return detail


@pytest.fixture
def make_zone_event(evidence_dir: Path) -> Callable[..., VisionEvent]:
    counter = {"seq": 0}

    def factory(
        event_id: str, zone: str, at: datetime, *, evidence: bool = True
    ) -> VisionEvent:
        counter["seq"] += 1
        refs: tuple[str, ...] = ()
        if evidence:
            (evidence_dir / "tmp").mkdir(exist_ok=True)
            Image.new("RGB", (16, 12), "black").save(
                evidence_dir / "tmp" / f"{event_id}.jpg", "JPEG"
            )
            refs = (f"tmp/{event_id}.jpg",)
        return VisionEvent(
            schema_version="1.0",
            event_id=event_id,
            event_type=f"bottle_in_{zone}_zone",
            station_id="st-01",
            camera_id="cam-01",
            camera_role="overview",
            occurred_at=at,
            emitted_at=at,
            frame_seq=counter["seq"],
            confidence=0.9,
            model=ModelRef(name="demo", version="1"),
            attributes={
                "object_class": "bottle",
                "zone": zone,
                "bbox": [0.1, 0.1, 0.2, 0.2],
            },
            evidence_refs=refs,
            correlation_key=f"st-01:{zone}:bottle",
        )

    return factory


@pytest.fixture
def event_with_evidence(make_zone_event: Callable[..., VisionEvent], now: datetime) -> VisionEvent:
    return make_zone_event("evt-1", "pickup", now)


@pytest.fixture
def event_payload(event_with_evidence: VisionEvent) -> dict[str, object]:
    payload = event_with_evidence.model_dump(mode="json")
    payload["evidence_refs"] = []
    return payload


@pytest.fixture
def open_alarm(db_session: Session, now: datetime) -> Alarm:
    alarm = upsert_alarm(
        db_session,
        dedup_key="station:st-01:camera:-:DEVICE_HEALTH",
        category=AlarmCategory.DEVICE_HEALTH,
        severity=AlarmSeverity.HIGH,
        reason_code=None,
        execution_id=None,
        station_id="st-01",
        camera_id=None,
        step_key=None,
        source_event_id=None,
        message="test alarm",
        now=now,
    )
    db_session.commit()
    return alarm
