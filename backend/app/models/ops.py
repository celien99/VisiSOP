from datetime import datetime
from typing import Any

from contracts.enums import MessageType
from contracts.runtime import HealthStatus
from sqlalchemy import Column, Index, String
from sqlmodel import Field, SQLModel

from app.models.columns import jsonb, timestamptz


class OutboxMessage(SQLModel, table=True):
    __tablename__ = "outbox_messages"
    __table_args__ = (Index("ix_outbox_messages_dispatched_at", "dispatched_at"),)

    id: str = Field(primary_key=True)
    message_id: str = Field(unique=True)
    type: MessageType = Field(sa_column=Column(String, nullable=False))
    station_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    created_at: datetime = Field(sa_column=timestamptz())
    dispatched_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    attempts: int = Field(default=0)
    last_error: str | None = None


class AuditRecord(SQLModel, table=True):
    __tablename__ = "audit_records"

    id: str = Field(primary_key=True)
    actor: str
    action: str
    object_type: str
    object_id: str
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    created_at: datetime = Field(sa_column=timestamptz())


class RuntimeHealthEvent(SQLModel, table=True):
    __tablename__ = "runtime_health_events"

    id: str = Field(primary_key=True)
    runtime_id: str = Field(index=True)
    status: HealthStatus = Field(sa_column=Column(String, nullable=False))
    metrics: dict[str, float] = Field(default_factory=dict, sa_column=jsonb())
    created_at: datetime = Field(sa_column=timestamptz())
