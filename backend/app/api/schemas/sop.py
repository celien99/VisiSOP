from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sop_dsl.schema import StepType

from app.models import SopVersionStatus


class SopCreate(BaseModel):
    key: str
    name: str
    dsl: dict[str, Any]


class SopDraftUpdate(BaseModel):
    dsl: dict[str, Any]


class SopIssue(BaseModel):
    code: str
    message: str
    step_key: str | None = None


class SopValidationRead(BaseModel):
    valid: bool
    issues: list[SopIssue]


class SopStepRead(BaseModel):
    key: str
    name: str
    type: StepType
    required: bool
    depends_on: list[str]


class SopVersionSummary(BaseModel):
    id: str
    sop_id: str
    version: int
    status: SopVersionStatus
    dsl_schema_version: str
    content_hash: str
    created_at: datetime
    published_at: datetime | None


class SopVersionRead(SopVersionSummary):
    dsl: dict[str, Any]
    steps: list[SopStepRead]


class SopRead(BaseModel):
    id: str
    key: str
    name: str
    created_at: datetime
    latest_published_version_id: str | None
    versions: list[SopVersionSummary]


class SopDetailRead(BaseModel):
    id: str
    key: str
    name: str
    created_at: datetime
    latest_published_version_id: str | None
    versions: list[SopVersionRead]
