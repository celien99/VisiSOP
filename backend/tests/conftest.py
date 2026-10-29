from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.api.deps import get_db
from app.core.db import engine
from app.main import app


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
