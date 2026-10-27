from collections.abc import Generator

from sqlmodel import Session

from app.api.deps import get_db
from app.core.config import Settings
from app.models import SQLModel


def test_get_db_yields_session() -> None:
    dependency: Generator[Session] = get_db()
    session = next(dependency)
    assert isinstance(session, Session)
    dependency.close()


def test_database_url_uses_psycopg_driver() -> None:
    settings = Settings(  # type: ignore[call-arg]
        PROJECT_NAME="test",
        DATABASE_URL="postgresql://user:pass@localhost/db",
    )
    assert str(settings.DATABASE_URL).startswith("postgresql+psycopg://")


def test_models_metadata_exists() -> None:
    assert SQLModel.metadata is not None
