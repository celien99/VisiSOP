import shutil
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete
from sqlmodel import Session, col, func, select

from app.application.audit import write_audit
from app.infrastructure.training_store import (
    DatasetExport,
    ExportAnnotation,
    ExportFrame,
    TrainingStore,
)
from app.models import (
    DatasetVersion,
    ModelArtifact,
    TrainingAnnotation,
    TrainingFrame,
    TrainingJob,
    TrainingJobStatus,
    TrainingProject,
    TrainingVideo,
    VideoStatus,
)


class TrainingNotFound(LookupError):
    pass


class TrainingConflict(RuntimeError):
    pass


class TrainingInvalid(ValueError):
    pass


def create_project(
    session: Session,
    *,
    key: str,
    name: str,
    classes: list[str],
    now: datetime,
) -> TrainingProject:
    _validate_classes(classes)
    existing = session.exec(
        select(TrainingProject).where(TrainingProject.key == key)
    ).first()
    if existing is not None:
        raise TrainingConflict(key)
    project = TrainingProject(
        id=str(uuid4()),
        key=key,
        name=name,
        classes=list(dict.fromkeys(classes)),
        created_at=now,
    )
    session.add(project)
    session.flush()
    return project


def update_project(
    session: Session,
    *,
    project_id: str,
    name: str | None,
    classes: list[str] | None,
) -> TrainingProject:
    project = get_project(session, project_id)
    if classes is not None:
        _validate_classes(classes)
        cleaned = list(dict.fromkeys(classes))
        removed = set(project.classes) - set(cleaned)
        if removed:
            in_use = session.exec(
                select(TrainingAnnotation.class_name)
                .join(
                    TrainingFrame,
                    col(TrainingAnnotation.frame_id) == col(TrainingFrame.id),
                )
                .join(
                    TrainingVideo,
                    col(TrainingFrame.video_id) == col(TrainingVideo.id),
                )
                .where(
                    TrainingVideo.project_id == project_id,
                    col(TrainingAnnotation.class_name).in_(removed),
                )
                .limit(1)
            ).first()
            if in_use is not None:
                raise TrainingInvalid(f"classes in use: {sorted(removed)}")
        project.classes = cleaned
    if name is not None:
        if not name.strip():
            raise TrainingInvalid("name must not be empty")
        project.name = name.strip()
    session.add(project)
    session.flush()
    return project


def list_projects(session: Session) -> list[TrainingProject]:
    return list(
        session.exec(
            select(TrainingProject).order_by(col(TrainingProject.created_at))
        ).all()
    )


def get_project(session: Session, project_id: str) -> TrainingProject:
    project = session.get(TrainingProject, project_id)
    if project is None:
        raise TrainingNotFound(project_id)
    return project


def get_project_by_key(session: Session, key: str) -> TrainingProject:
    project = session.exec(
        select(TrainingProject).where(TrainingProject.key == key)
    ).first()
    if project is None:
        raise TrainingNotFound(key)
    return project


def add_video(
    session: Session,
    store: TrainingStore,
    *,
    project_id: str,
    filename: str,
    suffix: str,
    data: bytes,
    now: datetime,
) -> TrainingVideo:
    project = get_project(session, project_id)
    video_id = str(uuid4())
    storage_key = store.save_video(project.key, video_id, suffix, data)
    status = VideoStatus.UPLOADED
    error: str | None = None
    duration_ms: int | None = None
    fps: float | None = None
    try:
        info = store.probe_video(storage_key)
        duration_ms = info.duration_ms
        fps = info.fps
    except Exception as exc:  # media boundary: OpenCV error text varies
        status = VideoStatus.FAILED
        error = str(exc)
    video = TrainingVideo(
        id=video_id,
        project_id=project.id,
        filename=filename,
        storage_key=storage_key,
        status=status,
        duration_ms=duration_ms,
        fps=fps,
        frame_count=0,
        error=error,
        created_at=now,
    )
    session.add(video)
    session.flush()
    return video


def get_video(session: Session, video_id: str) -> TrainingVideo:
    video = session.get(TrainingVideo, video_id)
    if video is None:
        raise TrainingNotFound(video_id)
    return video


def list_videos(session: Session, project_id: str) -> list[TrainingVideo]:
    get_project(session, project_id)
    return list(
        session.exec(
            select(TrainingVideo)
            .where(TrainingVideo.project_id == project_id)
            .order_by(col(TrainingVideo.created_at))
        ).all()
    )


def extract_video(
    session: Session,
    store: TrainingStore,
    *,
    video_id: str,
    fps: float,
    max_frames: int,
    dedupe: bool,
    now: datetime,
) -> list[TrainingFrame]:
    video = get_video(session, video_id)
    project = get_project(session, video.project_id)
    if video.frame_count > 0:
        raise TrainingConflict("frames already extracted")
    extracted = store.extract_frames(
        video.storage_key,
        project.key,
        video.id,
        fps=fps,
        max_frames=max_frames,
        dedupe=dedupe,
    )
    frames = [
        TrainingFrame(
            id=str(uuid4()),
            video_id=video.id,
            frame_index=item.frame_index,
            timestamp_ms=item.timestamp_ms,
            storage_key=item.storage_key,
            thumb_key=item.thumb_key,
            width=item.width,
            height=item.height,
            created_at=now,
        )
        for item in extracted
    ]
    session.add_all(frames)
    video.status = VideoStatus.READY
    video.frame_count = len(frames)
    video.error = None
    session.flush()
    return frames


def delete_video(session: Session, store: TrainingStore, *, video_id: str) -> None:
    """Remove a video with its frames, annotations, and stored files."""
    video = get_video(session, video_id)
    project = get_project(session, video.project_id)
    frames = list(
        session.exec(
            select(TrainingFrame).where(col(TrainingFrame.video_id) == video_id)
        ).all()
    )
    frame_ids = [frame.id for frame in frames]
    if frame_ids:
        session.exec(
            delete(TrainingAnnotation).where(
                col(TrainingAnnotation.frame_id).in_(frame_ids)
            )
        )
    session.exec(delete(TrainingFrame).where(col(TrainingFrame.video_id) == video_id))
    session.delete(video)
    session.flush()

    keys = [video.storage_key]
    for frame in frames:
        keys.extend((frame.storage_key, frame.thumb_key))
    for key in keys:
        try:
            store.resolve(key).unlink(missing_ok=True)
        except OSError:
            continue
    frames_dir = store.resolve(f"{store.project_dir(project.key)}/frames/{video_id}")
    if frames_dir.is_dir():
        shutil.rmtree(frames_dir, ignore_errors=True)


def list_frames(session: Session, video_id: str) -> list[tuple[TrainingFrame, int]]:
    get_video(session, video_id)
    frames = list(
        session.exec(
            select(TrainingFrame)
            .where(TrainingFrame.video_id == video_id)
            .order_by(col(TrainingFrame.frame_index))
        ).all()
    )
    counts = dict(
        session.exec(
            select(TrainingAnnotation.frame_id, func.count())
            .where(col(TrainingAnnotation.frame_id).in_([frame.id for frame in frames]))
            .group_by(col(TrainingAnnotation.frame_id))
        ).all()
    )
    return [(frame, int(counts.get(frame.id, 0))) for frame in frames]


def get_frame(session: Session, frame_id: str) -> TrainingFrame:
    frame = session.get(TrainingFrame, frame_id)
    if frame is None:
        raise TrainingNotFound(frame_id)
    return frame


def frame_annotations(session: Session, frame_id: str) -> list[TrainingAnnotation]:
    get_frame(session, frame_id)
    return list(
        session.exec(
            select(TrainingAnnotation)
            .where(TrainingAnnotation.frame_id == frame_id)
            .order_by(col(TrainingAnnotation.created_at))
        ).all()
    )


def replace_annotations(
    session: Session,
    *,
    frame_id: str,
    boxes: list[dict[str, Any]],
    now: datetime,
) -> list[TrainingAnnotation]:
    frame = get_frame(session, frame_id)
    video = get_video(session, frame.video_id)
    project = get_project(session, video.project_id)
    known = set(project.classes)
    session.exec(
        delete(TrainingAnnotation).where(col(TrainingAnnotation.frame_id) == frame_id)
    )
    annotations: list[TrainingAnnotation] = []
    for box in boxes:
        class_name = str(box["class_name"])
        if class_name not in known:
            raise TrainingInvalid(f"unknown class: {class_name}")
        x1, y1 = float(box["x1"]), float(box["y1"])
        x2, y2 = float(box["x2"]), float(box["y2"])
        if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
            raise TrainingInvalid("boxes must be normalized and non-empty")
        annotations.append(
            TrainingAnnotation(
                id=str(uuid4()),
                frame_id=frame_id,
                class_name=class_name,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                created_at=now,
                updated_at=now,
            )
        )
    session.add_all(annotations)
    session.flush()
    return annotations


def project_stats(session: Session, project_id: str) -> dict[str, Any]:
    get_project(session, project_id)
    video_ids = list(
        session.exec(
            select(TrainingVideo.id).where(TrainingVideo.project_id == project_id)
        ).all()
    )
    frame_ids = (
        list(
            session.exec(
                select(TrainingFrame.id).where(
                    col(TrainingFrame.video_id).in_(video_ids)
                )
            ).all()
        )
        if video_ids
        else []
    )
    labeled = (
        session.exec(
            select(func.count(func.distinct(TrainingAnnotation.frame_id))).where(
                col(TrainingAnnotation.frame_id).in_(frame_ids)
            )
        ).one()
        if frame_ids
        else 0
    )
    per_class = (
        dict(
            session.exec(
                select(TrainingAnnotation.class_name, func.count())
                .where(col(TrainingAnnotation.frame_id).in_(frame_ids))
                .group_by(col(TrainingAnnotation.class_name))
            ).all()
        )
        if frame_ids
        else {}
    )
    return {
        "videos": len(video_ids),
        "frames": len(frame_ids),
        "labeled_frames": int(labeled),
        "annotations": int(sum(per_class.values())),
        "per_class": {key: int(value) for key, value in per_class.items()},
    }


def create_dataset(
    session: Session,
    store: TrainingStore,
    *,
    project_id: str,
    val_ratio: float,
    now: datetime,
) -> DatasetVersion:
    project = get_project(session, project_id)
    if not 0.0 <= val_ratio < 1.0:
        raise TrainingInvalid("val_ratio must be in [0, 1)")
    frame_ids = list(
        session.exec(
            select(TrainingAnnotation.frame_id)
            .join(
                TrainingFrame,
                col(TrainingAnnotation.frame_id) == col(TrainingFrame.id),
            )
            .join(
                TrainingVideo,
                col(TrainingFrame.video_id) == col(TrainingVideo.id),
            )
            .where(TrainingVideo.project_id == project_id)
            .distinct()
        ).all()
    )
    if len(frame_ids) < 5:
        raise TrainingInvalid("at least five labelled frames are required")
    frames: list[ExportFrame] = []
    for frame_id in frame_ids:
        frame = get_frame(session, frame_id)
        boxes = frame_annotations(session, frame_id)
        frames.append(
            ExportFrame(
                frame_id=frame.id,
                image_path=store.resolve(frame.storage_key),
                annotations=tuple(
                    ExportAnnotation(
                        class_name=box.class_name,
                        x1=box.x1,
                        y1=box.y1,
                        x2=box.x2,
                        y2=box.y2,
                    )
                    for box in boxes
                ),
            )
        )
    last = session.exec(
        select(func.max(DatasetVersion.version)).where(
            DatasetVersion.project_id == project_id
        )
    ).one()
    version = int(last or 0) + 1
    export: DatasetExport = store.save_dataset(
        project.key,
        version,
        classes=project.classes,
        frames=frames,
        val_ratio=val_ratio,
    )
    dataset = DatasetVersion(
        id=str(uuid4()),
        project_id=project_id,
        version=version,
        frame_count=export.frame_count,
        train_count=export.train_count,
        val_count=export.val_count,
        storage_key=export.storage_key,
        manifest=export.manifest,
        created_at=now,
    )
    session.add(dataset)
    session.flush()
    return dataset


def list_datasets(session: Session, project_id: str) -> list[DatasetVersion]:
    get_project(session, project_id)
    return list(
        session.exec(
            select(DatasetVersion)
            .where(DatasetVersion.project_id == project_id)
            .order_by(col(DatasetVersion.version).desc())
        ).all()
    )


def create_job(
    session: Session,
    *,
    project_id: str,
    dataset_version_id: str,
    epochs: int,
    now: datetime,
) -> TrainingJob:
    get_project(session, project_id)
    dataset = session.get(DatasetVersion, dataset_version_id)
    if dataset is None or dataset.project_id != project_id:
        raise TrainingNotFound(dataset_version_id)
    if not 1 <= epochs <= 500:
        raise TrainingInvalid("epochs must be between 1 and 500")
    running = session.exec(
        select(TrainingJob).where(
            TrainingJob.project_id == project_id,
            col(TrainingJob.status).in_(
                (TrainingJobStatus.QUEUED, TrainingJobStatus.RUNNING)
            ),
        )
    ).first()
    if running is not None:
        raise TrainingConflict("a training job is already queued or running")
    job = TrainingJob(
        id=str(uuid4()),
        project_id=project_id,
        dataset_version_id=dataset_version_id,
        status=TrainingJobStatus.QUEUED,
        progress=0,
        epochs=epochs,
        metrics={},
        created_at=now,
    )
    session.add(job)
    session.flush()
    return job


def get_job(session: Session, job_id: str) -> TrainingJob:
    job = session.get(TrainingJob, job_id)
    if job is None:
        raise TrainingNotFound(job_id)
    return job


def list_jobs(session: Session, project_id: str) -> list[TrainingJob]:
    get_project(session, project_id)
    return list(
        session.exec(
            select(TrainingJob)
            .where(TrainingJob.project_id == project_id)
            .order_by(col(TrainingJob.created_at).desc())
        ).all()
    )


def list_models(session: Session, project_id: str) -> list[ModelArtifact]:
    get_project(session, project_id)
    return list(
        session.exec(
            select(ModelArtifact)
            .where(ModelArtifact.project_id == project_id)
            .order_by(col(ModelArtifact.version).desc())
        ).all()
    )


def get_model(session: Session, model_id: str) -> ModelArtifact:
    model = session.get(ModelArtifact, model_id)
    if model is None:
        raise TrainingNotFound(model_id)
    return model


def activate_model(
    session: Session, *, model_id: str, actor: str, now: datetime
) -> ModelArtifact:
    model = get_model(session, model_id)
    if model.manifest.get("validated") is not True:
        raise TrainingInvalid("model artifact was not validated")
    active = session.exec(
        select(ModelArtifact).where(
            ModelArtifact.project_id == model.project_id,
            col(ModelArtifact.active).is_(True),
        )
    ).all()
    for other in active:
        if other.id != model.id:
            other.active = False
    # The partial unique index allows one active row per project, so the
    # deactivation must reach the database before the new activation.
    session.flush()
    model.active = True
    write_audit(
        session,
        actor=actor,
        action="training.model_activated",
        object_type="model_artifact",
        object_id=model.id,
        detail={"project_id": model.project_id, "version": model.version},
        now=now,
    )
    session.flush()
    return model


def active_model(
    session: Session, project_key: str
) -> tuple[TrainingProject, ModelArtifact] | None:
    project = get_project_by_key(session, project_key)
    model = session.exec(
        select(ModelArtifact).where(
            ModelArtifact.project_id == project.id,
            col(ModelArtifact.active).is_(True),
        )
    ).first()
    if model is None or model.manifest.get("validated") is not True:
        return None
    return project, model


def _validate_classes(classes: list[str]) -> None:
    if not classes:
        raise TrainingInvalid("at least one class is required")
    cleaned = [name.strip() for name in classes]
    if any(not name for name in cleaned):
        raise TrainingInvalid("class names must not be empty")
    if len(set(cleaned)) != len(cleaned):
        raise TrainingInvalid("class names must be unique")
