from datetime import UTC, datetime

from contracts.runtime import HealthStatus
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep
from app.api.schemas.health import HealthSummaryRead
from app.application import station_service
from app.application.runtime_registry import runtime_registry

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/summary", response_model=HealthSummaryRead, name="get_health_summary")
def get_health_summary(session: SessionDep) -> HealthSummaryRead:
    try:
        session.connection().execute(text("SELECT 1"))
        database = HealthStatus.HEALTHY
    except SQLAlchemyError:
        database = HealthStatus.UNAVAILABLE
    now = datetime.now(UTC)
    return HealthSummaryRead(
        database=database,
        server_time=now,
        runtimes=runtime_registry.read_all(now),
        cameras=station_service.list_cameras(session, now=now),
    )
