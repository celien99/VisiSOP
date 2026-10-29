from datetime import datetime
from typing import Any

from contracts.runtime import HealthStatus
from pydantic import BaseModel, Field


class CameraCreate(BaseModel):
    code: str
    name: str
    runtime_id: str
    source_type: str
    source_config: dict[str, Any] = Field(default_factory=dict)
    preview_url: str | None = None
    snapshot_url: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    runtime_id: str | None = None
    source_type: str | None = None
    source_config: dict[str, Any] | None = None
    preview_url: str | None = None
    snapshot_url: str | None = None


class CameraRead(BaseModel):
    id: str
    code: str
    name: str
    runtime_id: str
    source_type: str
    preview_url: str | None
    snapshot_url: str | None
    health: HealthStatus
    last_frame_at: datetime | None
    created_at: datetime


class CameraHealthRead(BaseModel):
    camera_id: str
    status: HealthStatus
    last_frame_at: datetime | None
    fps: float | None
    inference_ms: float | None
    dropped_frames: int | None
    error: str | None


class CameraCommandRead(BaseModel):
    camera_id: str
    command: str
