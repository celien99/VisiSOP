from datetime import datetime

from contracts.enums import ProcessingResult, ReasonCode
from pydantic import BaseModel


class EventIngestRead(BaseModel):
    event_id: str
    result: ProcessingResult
    execution_id: str | None
    reason_code: ReasonCode | None
    detail: str | None
    received_at: datetime


class EventAssignRequest(BaseModel):
    execution_id: str


class EventRead(BaseModel):
    event_id: str
    event_type: str
    station_id: str
    camera_id: str
    occurred_at: datetime
    result: ProcessingResult
    reason_code: ReasonCode | None
    execution_id: str | None
    candidate_ids: list[str]
    resolution_method: str | None
    detail: str | None
