from datetime import datetime

from contracts.enums import ReasonCode
from pydantic import BaseModel

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
