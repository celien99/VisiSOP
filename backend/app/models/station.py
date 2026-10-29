from datetime import datetime
from typing import Any

from contracts.enums import CameraRole
from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from app.models.columns import jsonb, timestamptz


class Station(SQLModel, table=True):
    __tablename__ = "stations"

    id: str = Field(primary_key=True)
    code: str = Field(unique=True, index=True)
    name: str
    zone: str | None = None
    created_at: datetime = Field(sa_column=timestamptz())


class Camera(SQLModel, table=True):
    __tablename__ = "cameras"

    id: str = Field(primary_key=True)
    code: str = Field(unique=True, index=True)
    name: str
    runtime_id: str = Field(index=True)
    source_type: str
    source_config: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    preview_url: str | None = None
    snapshot_url: str | None = None
    created_at: datetime = Field(sa_column=timestamptz())


class StationCameraBinding(SQLModel, table=True):
    __tablename__ = "station_camera_bindings"

    id: str = Field(primary_key=True)
    station_id: str = Field(foreign_key="stations.id", index=True)
    camera_id: str = Field(foreign_key="cameras.id", index=True)
    role: CameraRole = Field(sa_column=Column(String, nullable=False))
    valid_from: datetime = Field(sa_column=timestamptz())
    valid_to: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
