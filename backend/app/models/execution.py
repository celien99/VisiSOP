from datetime import datetime
from typing import Any

from contracts.enums import ReasonCode
from sqlalchemy import Column, Index, String
from sqlmodel import Field, SQLModel

from app.domain.sop.model import ExecutionStatus, StepStatus
from app.models.columns import jsonb, timestamptz


class SOPExecution(SQLModel, table=True):
    __tablename__ = "sop_executions"
    __table_args__ = (
        Index("ix_sop_executions_station_status", "station_id", "status"),
    )

    id: str = Field(primary_key=True)
    station_id: str = Field(foreign_key="stations.id")
    sop_version_id: str = Field(foreign_key="sop_versions.id")
    workpiece_id: str | None = None
    status: ExecutionStatus = Field(sa_column=Column(String, nullable=False))
    version: int = Field(default=1)
    started_at: datetime = Field(sa_column=timestamptz())
    finished_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    paused_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    total_paused_ms: int = Field(default=0)
    accept_events_until: datetime = Field(sa_column=timestamptz())
    created_at: datetime = Field(sa_column=timestamptz())


class StepExecution(SQLModel, table=True):
    __tablename__ = "step_executions"

    execution_id: str = Field(foreign_key="sop_executions.id", primary_key=True)
    step_key: str = Field(primary_key=True)
    status: StepStatus = Field(sa_column=Column(String, nullable=False))
    activated_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    deadline_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    matched_events: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=jsonb()
    )
    reason_code: ReasonCode | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    skipped_reason: str | None = None
    review_reason: str | None = None
    review_comment: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    updated_at: datetime = Field(sa_column=timestamptz())
