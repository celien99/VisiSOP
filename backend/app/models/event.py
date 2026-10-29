from datetime import datetime
from typing import Any

from contracts.enums import ProcessingResult, ReasonCode
from sqlalchemy import Column, Index, String
from sqlmodel import Field, SQLModel

from app.models.columns import jsonb, timestamptz


class VisionEventRow(SQLModel, table=True):
    __tablename__ = "vision_events"
    __table_args__ = (
        Index("ix_vision_events_station_occurred", "station_id", "occurred_at"),
        Index("ix_vision_events_camera_id", "camera_id"),
        Index("ix_vision_events_execution_id", "execution_id"),
    )

    event_id: str = Field(primary_key=True)
    event_type: str
    station_id: str
    camera_id: str
    camera_role: str | None = None
    occurred_at: datetime = Field(sa_column=timestamptz())
    emitted_at: datetime = Field(sa_column=timestamptz())
    frame_seq: int
    confidence: float
    model: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    observation_ids: list[str] = Field(default_factory=list, sa_column=jsonb())
    evidence_refs: list[str] = Field(default_factory=list, sa_column=jsonb())
    attributes: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    correlation_key: str | None = None
    execution_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())


class EventProcessingReceipt(SQLModel, table=True):
    __tablename__ = "event_processing_receipts"

    event_id: str = Field(foreign_key="vision_events.event_id", primary_key=True)
    result: ProcessingResult = Field(sa_column=Column(String, nullable=False))
    reason_code: ReasonCode | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    execution_id: str | None = None
    candidate_ids: list[str] = Field(default_factory=list, sa_column=jsonb())
    resolution_method: str | None = None
    resolver_rule_version: str | None = None
    rule_version: str | None = None
    dsl_version: str | None = None
    detail: str | None = None
    processed_at: datetime = Field(sa_column=timestamptz())
