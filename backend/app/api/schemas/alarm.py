from datetime import datetime

from contracts.enums import AlarmCategory, AlarmSeverity, AlarmStatus, ReasonCode
from pydantic import BaseModel, Field


class AlarmActionRequest(BaseModel):
    operator: str = Field(min_length=1)
    comment: str | None = None


class AlarmRead(BaseModel):
    id: str
    execution_id: str | None
    station_id: str
    camera_id: str | None
    category: AlarmCategory
    severity: AlarmSeverity
    status: AlarmStatus
    reason_code: ReasonCode | None
    step_key: str | None
    message: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    comment: str | None
