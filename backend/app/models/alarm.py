from datetime import datetime

from contracts.enums import AlarmCategory, AlarmSeverity, AlarmStatus, ReasonCode
from sqlalchemy import Column, Index, String, text
from sqlmodel import Field, SQLModel

from app.models.columns import timestamptz


class Alarm(SQLModel, table=True):
    __tablename__ = "alarms"
    __table_args__ = (
        Index(
            "uq_alarms_open_dedup_key",
            "dedup_key",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'ACKNOWLEDGED')"),
        ),
        Index(
            "ix_alarms_status_severity_first_seen",
            "status",
            "severity",
            "first_seen_at",
        ),
    )

    # Ids are denormalized on purpose: an alarm outlives the row it points at
    # and is also raised for ids the backend has not persisted (device alarms).
    id: str = Field(primary_key=True)
    dedup_key: str
    execution_id: str | None = Field(default=None, index=True)
    station_id: str = Field(index=True)
    camera_id: str | None = None
    category: AlarmCategory = Field(sa_column=Column(String, nullable=False))
    severity: AlarmSeverity = Field(sa_column=Column(String, nullable=False))
    status: AlarmStatus = Field(sa_column=Column(String, nullable=False))
    reason_code: ReasonCode | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    step_key: str | None = None
    source_event_id: str | None = None
    message: str = ""
    first_seen_at: datetime = Field(sa_column=timestamptz())
    last_seen_at: datetime = Field(sa_column=timestamptz())
    occurrence_count: int = Field(default=1)
    acknowledged_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    acknowledged_by: str | None = None
    resolved_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    resolved_by: str | None = None
    comment: str | None = None
