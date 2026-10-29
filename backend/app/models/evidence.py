from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from app.models.columns import timestamptz


class EvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PENDING_VERIFY = "PENDING_VERIFY"
    MISSING = "MISSING"


class EvidenceAsset(SQLModel, table=True):
    __tablename__ = "evidence_assets"

    id: str = Field(primary_key=True)
    event_id: str = Field(foreign_key="vision_events.event_id", index=True)
    storage_key: str = Field(unique=True)
    sha256: str | None = Field(default=None, index=True)
    byte_size: int | None = None
    width: int | None = None
    height: int | None = None
    status: EvidenceStatus = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(sa_column=timestamptz())
    verified_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )


class EventEvidenceLink(SQLModel, table=True):
    __tablename__ = "event_evidence_links"

    event_id: str = Field(foreign_key="vision_events.event_id", primary_key=True)
    evidence_id: str = Field(foreign_key="evidence_assets.id", primary_key=True)
