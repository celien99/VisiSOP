from datetime import datetime

from contracts.runtime import HealthStatus
from pydantic import BaseModel


class RuntimeRead(BaseModel):
    runtime_id: str
    base_url: str
    preview_base_url: str | None
    version: str
    camera_ids: list[str]
    status: HealthStatus
    last_heartbeat_at: datetime | None
