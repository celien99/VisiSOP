from datetime import UTC, datetime

from contracts.runtime import RuntimeHeartbeat, RuntimeRegistration
from fastapi import APIRouter, HTTPException

from app.api.schemas.runtime import RuntimeRead
from app.application.runtime_registry import RuntimeNotFound, runtime_registry

router = APIRouter(prefix="/runtimes", tags=["runtimes"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("/register", response_model=RuntimeRead, name="register_runtime")
def register_runtime(payload: RuntimeRegistration) -> RuntimeRead:
    entry = runtime_registry.register(payload, _now())
    return runtime_registry.read(entry, _now())


@router.post(
    "/{runtime_id}/heartbeat",
    response_model=RuntimeRead,
    name="runtime_heartbeat",
)
def runtime_heartbeat(runtime_id: str, payload: RuntimeHeartbeat) -> RuntimeRead:
    try:
        entry = runtime_registry.heartbeat(runtime_id, payload, _now())
    except RuntimeNotFound:
        raise HTTPException(status_code=404, detail="runtime not registered") from None
    return runtime_registry.read(entry, _now())


@router.get("", response_model=list[RuntimeRead], name="list_runtimes")
def list_runtimes() -> list[RuntimeRead]:
    return runtime_registry.read_all(_now())
