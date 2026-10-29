from datetime import datetime
from enum import StrEnum

from contracts.enums import ReasonCode, ReviewDecision
from pydantic import BaseModel, Field
from sop_dsl.schema import StepType

from app.api.schemas.evidence import EvidenceRead
from app.domain.sop.model import ExecutionStatus, StepStatus


class StepSummaryRead(BaseModel):
    key: str
    name: str
    status: StepStatus
    reason_code: ReasonCode | None
    started_at: datetime | None


class ExecutionSummaryRead(BaseModel):
    id: str
    sop_key: str
    sop_version: int
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    current_step_key: str | None
    current_step_name: str | None
    current_step_status: StepStatus | None


class ExecutionCreate(BaseModel):
    sop_version_id: str
    workpiece_id: str | None = None


class StepReviewRequest(BaseModel):
    operator: str = Field(min_length=1)
    decision: ReviewDecision
    reason: str = Field(min_length=1)
    comment: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class StepSkipRequest(BaseModel):
    operator: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    comment: str | None = None


class ExecutionAbortRequest(BaseModel):
    reason: str = Field(min_length=1)


class MatchedEventRead(BaseModel):
    event_id: str
    event_type: str
    confidence: float
    occurred_at: datetime
    camera_id: str
    camera_role: str | None
    correlation_key: str | None
    accepted: bool


class StepRead(BaseModel):
    key: str
    name: str
    type: StepType
    required: bool
    status: StepStatus
    reason_code: ReasonCode | None
    activated_at: datetime | None
    deadline_at: datetime | None
    matched_events: list[MatchedEventRead]
    evidence: list[EvidenceRead]
    skipped_reason: str | None
    review_reason: str | None
    review_comment: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    allowed_actions: list[str]


class ExecutionDetailRead(BaseModel):
    id: str
    station_id: str
    sop_key: str
    sop_version: int
    sop_content_hash: str
    status: ExecutionStatus
    workpiece_id: str | None
    started_at: datetime
    finished_at: datetime | None
    paused_at: datetime | None
    total_paused_ms: int
    accept_events_until: datetime
    steps: list[StepRead]
    allowed_actions: list[str]
    server_time: datetime


class TimelineItemType(StrEnum):
    EVENT = "EVENT"
    STEP = "STEP"
    ALARM = "ALARM"


class TimelineItemRead(BaseModel):
    type: TimelineItemType
    at: datetime
    title: str
    detail: str | None
    step_key: str | None
    reason_code: ReasonCode | None
    event_type: str | None
    confidence: float | None
    model: str | None
