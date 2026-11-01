from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.application import training_service
from app.core.config import settings
from app.infrastructure.training_store import (
    ExportAnnotation,
    ExportFrame,
    TrainingStore,
)
from app.models import TrainingJobStatus, VideoStatus


def write_video(path: Path, *, frames: int = 60, fps: int = 10) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), float(fps), (64, 48)
    )
    assert writer.isOpened()
    for index in range(frames):
        writer.write(np.full((48, 64, 3), index * 7 % 255, dtype=np.uint8))
    writer.release()


@pytest.fixture
def training_store(tmp_path, monkeypatch) -> TrainingStore:
    monkeypatch.setattr(settings, "TRAINING_DIR", tmp_path / "training")
    return TrainingStore(tmp_path / "training")


@pytest.fixture
def clip(tmp_path) -> Path:
    path = tmp_path / "clip.avi"
    write_video(path)
    return path


def test_store_probes_extracts_and_exports(
    training_store: TrainingStore, clip: Path, tmp_path
) -> None:
    key = training_store.save_video("p1", "v1", ".avi", clip.read_bytes())
    info = training_store.probe_video(key)
    assert info.fps == 10
    assert info.frame_count == 60

    frames = training_store.extract_frames(
        key, "p1", "v1", fps=5, max_frames=100
    )
    assert len(frames) == 30
    assert (tmp_path / "training" / frames[0].storage_key).is_file()
    assert (tmp_path / "training" / frames[0].thumb_key).is_file()

    export_frames = [
        ExportFrame(
            frame_id=f"f{index}",
            image_path=training_store.resolve(frame.storage_key),
            annotations=(
                ExportAnnotation("remote", 0.1, 0.1, 0.5, 0.5),
                ExportAnnotation("battery", 0.6, 0.6, 0.8, 0.8),
            ),
        )
        for index, frame in enumerate(frames[:5])
    ]
    export = training_store.save_dataset(
        "p1", 1, classes=["remote", "battery"], frames=export_frames, val_ratio=0.2
    )
    assert export.frame_count == 5
    assert export.train_count + export.val_count == 5
    dataset_dir = training_store.resolve(export.storage_key)
    assert (dataset_dir / "data.yaml").is_file()
    label = next((dataset_dir / "labels").rglob("*.txt")).read_text()
    assert label.split()[0] in {"0", "1"}


def test_service_flow(
    db_session, training_store: TrainingStore, clip: Path, now: datetime
) -> None:
    project = training_service.create_project(
        db_session,
        key="remote",
        name="Remote",
        classes=["remote", "battery"],
        now=now,
    )
    video = training_service.add_video(
        db_session,
        training_store,
        project_id=project.id,
        filename="clip.avi",
        suffix=".avi",
        data=clip.read_bytes(),
        now=now,
    )
    assert video.status is VideoStatus.UPLOADED
    assert video.duration_ms == 6000

    frames = training_service.extract_video(
        db_session,
        training_store,
        video_id=video.id,
        fps=5,
        max_frames=100,
        now=now,
    )
    assert len(frames) == 30
    for frame in frames[:5]:
        training_service.replace_annotations(
            db_session,
            frame_id=frame.id,
            boxes=[
                {"class_name": "remote", "x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5}
            ],
            now=now,
        )

    stats = training_service.project_stats(db_session, project.id)
    assert stats["frames"] == 30
    assert stats["labeled_frames"] == 5

    dataset = training_service.create_dataset(
        db_session, training_store, project_id=project.id, val_ratio=0.2, now=now
    )
    assert dataset.frame_count == 5

    job = training_service.create_job(
        db_session,
        project_id=project.id,
        dataset_version_id=dataset.id,
        epochs=10,
        now=now,
    )
    assert job.status is TrainingJobStatus.QUEUED

    with pytest.raises(training_service.TrainingInvalid):
        training_service.replace_annotations(
            db_session,
            frame_id=frames[0].id,
            boxes=[
                {"class_name": "unknown", "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}
            ],
            now=now,
        )
