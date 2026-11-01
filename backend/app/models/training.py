from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Index, String, text
from sqlmodel import Field, SQLModel

from app.models.columns import jsonb, timestamptz


class VideoStatus(StrEnum):
    UPLOADED = "UPLOADED"
    READY = "READY"
    FAILED = "FAILED"


class TrainingJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TrainingProject(SQLModel, table=True):
    __tablename__ = "training_projects"

    id: str = Field(primary_key=True)
    key: str = Field(unique=True, index=True)
    name: str
    classes: list[str] = Field(default_factory=list, sa_column=jsonb())
    created_at: datetime = Field(sa_column=timestamptz())


class TrainingVideo(SQLModel, table=True):
    __tablename__ = "training_videos"
    __table_args__ = (Index("ix_training_videos_project", "project_id", "created_at"),)

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="training_projects.id")
    filename: str
    storage_key: str
    status: VideoStatus = Field(sa_column=Column(String, nullable=False))
    duration_ms: int | None = None
    fps: float | None = None
    frame_count: int = Field(default=0)
    error: str | None = None
    created_at: datetime = Field(sa_column=timestamptz())


class TrainingFrame(SQLModel, table=True):
    __tablename__ = "training_frames"
    __table_args__ = (
        Index(
            "ix_training_frames_video_index",
            "video_id",
            "frame_index",
            unique=True,
        ),
    )

    id: str = Field(primary_key=True)
    video_id: str = Field(foreign_key="training_videos.id")
    frame_index: int
    timestamp_ms: int
    storage_key: str
    thumb_key: str
    width: int
    height: int
    created_at: datetime = Field(sa_column=timestamptz())


class TrainingAnnotation(SQLModel, table=True):
    __tablename__ = "training_annotations"
    __table_args__ = (Index("ix_training_annotations_frame", "frame_id"),)

    id: str = Field(primary_key=True)
    frame_id: str = Field(foreign_key="training_frames.id")
    class_name: str
    x1: float
    y1: float
    x2: float
    y2: float
    created_at: datetime = Field(sa_column=timestamptz())
    updated_at: datetime = Field(sa_column=timestamptz())


class DatasetVersion(SQLModel, table=True):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        Index(
            "ix_dataset_versions_project_version", "project_id", "version", unique=True
        ),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="training_projects.id")
    version: int
    frame_count: int
    train_count: int
    val_count: int
    storage_key: str
    manifest: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    created_at: datetime = Field(sa_column=timestamptz())


class TrainingJob(SQLModel, table=True):
    __tablename__ = "training_jobs"
    __table_args__ = (Index("ix_training_jobs_project", "project_id", "created_at"),)

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="training_projects.id")
    dataset_version_id: str = Field(foreign_key="dataset_versions.id")
    status: TrainingJobStatus = Field(sa_column=Column(String, nullable=False))
    progress: int = Field(default=0)
    epochs: int
    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    artifact_key: str | None = None
    log_key: str | None = None
    error: str | None = None
    created_at: datetime = Field(sa_column=timestamptz())
    started_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=timestamptz(nullable=True)
    )


class ModelArtifact(SQLModel, table=True):
    __tablename__ = "model_artifacts"
    __table_args__ = (
        Index(
            "ix_model_artifacts_active",
            "project_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="training_projects.id")
    training_job_id: str = Field(foreign_key="training_jobs.id")
    version: int
    onnx_key: str
    names_key: str
    manifest: dict[str, Any] = Field(default_factory=dict, sa_column=jsonb())
    active: bool = Field(default=False)
    created_at: datetime = Field(sa_column=timestamptz())
