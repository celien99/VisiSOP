import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.api.deps import get_db
from app.application.sop_service import create_sop, publish_sop
from app.core.db import engine
from app.main import app
from app.models import SOPVersion

DEMO_SOP_PATH = Path(__file__).parents[1] / "app" / "seed" / "bottle_transfer.json"


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


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
