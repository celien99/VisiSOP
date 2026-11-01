from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.training import TrainingJobStatus, VideoStatus


class ProjectCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1)
    classes: list[str] = Field(min_length=1)

    @field_validator("classes")
    @classmethod
    def _clean_classes(cls, value: list[str]) -> list[str]:
        cleaned = [name.strip() for name in value]
        if any(not name for name in cleaned):
            raise ValueError("class names must not be empty")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("class names must be unique")
        return cleaned


class ProjectRead(BaseModel):
    id: str
    key: str
    name: str
    classes: list[str]
    created_at: datetime


class VideoRead(BaseModel):
    id: str
    project_id: str
    filename: str
    status: VideoStatus
    duration_ms: int | None
    fps: float | None
    frame_count: int
    error: str | None
    created_at: datetime


class ExtractRequest(BaseModel):
    fps: float = Field(default=1.0, gt=0, le=30)
    max_frames: int = Field(default=500, ge=1, le=5000)


class FrameRead(BaseModel):
    id: str
    video_id: str
    frame_index: int
    timestamp_ms: int
    width: int
    height: int
    image_url: str
    thumb_url: str
    annotation_count: int


class AnnotationInput(BaseModel):
    class_name: str
    x1: float
    y1: float
    x2: float
    y2: float


class AnnotationsUpdate(BaseModel):
    annotations: list[AnnotationInput] = Field(default_factory=list)


class AnnotationRead(BaseModel):
    id: str
    frame_id: str
    class_name: str
    x1: float
    y1: float
    x2: float
    y2: float


class StatsRead(BaseModel):
    videos: int
    frames: int
    labeled_frames: int
    annotations: int
    per_class: dict[str, int]


class DatasetCreate(BaseModel):
    val_ratio: float = Field(default=0.2, ge=0.0, lt=1.0)


class DatasetRead(BaseModel):
    id: str
    version: int
    frame_count: int
    train_count: int
    val_count: int
    storage_key: str
    created_at: datetime


class JobCreate(BaseModel):
    dataset_version_id: str
    epochs: int = Field(default=50, ge=1, le=500)


class JobRead(BaseModel):
    id: str
    project_id: str
    dataset_version_id: str
    status: TrainingJobStatus
    progress: int
    epochs: int
    metrics: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ModelRead(BaseModel):
    id: str
    project_id: str
    version: int
    training_job_id: str
    metrics: dict[str, Any]
    manifest: dict[str, Any]
    active: bool
    created_at: datetime
    artifact_url: str
    names_url: str


class ActivationRequest(BaseModel):
    operator: str = Field(min_length=1)


class ActiveModelRead(BaseModel):
    id: str
    project_key: str
    version: int
    classes: list[str]
    metrics: dict[str, Any]
    onnx_url: str
    names_url: str
