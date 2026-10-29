import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.execution import ExecutionDetailRead
from app.application.runtime_registry import runtime_registry
from app.application.sop_service import create_sop, publish_sop
from app.core.config import settings
from app.core.db import engine
from app.main import app
from app.models import (
    Camera,
    SOPVersion,
    Station,
    StationCameraBinding,
)
from contracts.enums import CameraRole

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
    client: TestClient, published_sop: SOPVersion, seeded_station: Station
) -> ExecutionDetailRead:
    response = client.post(
        "/api/stations/st-01/executions",
        json={"sop_version_id": published_sop.id},
    )
    assert response.status_code == 201, response.text
    return ExecutionDetailRead.model_validate(response.json())
