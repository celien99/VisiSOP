import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import select

from app.application import training_service
from app.core.config import settings
from app.infrastructure.training_store import TrainingStore
from app.models import DatasetVersion, ModelArtifact, TrainingJob, TrainingJobStatus
from app.workers.training_worker import Spawned, execute_job


class FakeProcess:
    def __init__(self, code: int) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code

    def wait(self) -> int:
        return self.code


@pytest.fixture
def training_store(tmp_path, monkeypatch) -> TrainingStore:
    monkeypatch.setattr(settings, "TRAINING_DIR", tmp_path / "training")
    return TrainingStore(tmp_path / "training")


def make_job(db_session, store: TrainingStore, now: datetime) -> TrainingJob:
    project = training_service.create_project(
        db_session,
        key="remote",
        name="Remote",
        classes=["remote"],
        now=now,
    )
    data_yaml = store.resolve("projects/remote/datasets/v1/data.yaml")
    data_yaml.parent.mkdir(parents=True, exist_ok=True)
    data_yaml.write_text("path: x\n", encoding="utf-8")
    dataset = DatasetVersion(
        id=str(uuid4()),
        project_id=project.id,
        version=1,
        frame_count=10,
        train_count=8,
        val_count=2,
        storage_key="projects/remote/datasets/v1",
        manifest={"data_yaml": "projects/remote/datasets/v1/data.yaml"},
        created_at=now,
    )
    db_session.add(dataset)
    db_session.flush()
    return training_service.create_job(
        db_session,
        project_id=project.id,
        dataset_version_id=dataset.id,
        epochs=2,
        now=now,
    )


def test_successful_job_stores_the_model(
    db_session, training_store: TrainingStore, now: datetime
) -> None:
    job = make_job(db_session, training_store, now)

    def spawn(run) -> Spawned:
        run.onnx_path.parent.mkdir(parents=True, exist_ok=True)
        run.onnx_path.write_bytes(b"onnx")
        run.names_path.write_text("remote\n", encoding="utf-8", newline="\n")
        run.metrics_path.write_text(
            json.dumps({"metrics": {"mAP50": 0.9}, "names": ["remote"]}),
            encoding="utf-8",
        )
        run.progress_path.write_text(
            json.dumps(
                {
                    "status": "SUCCEEDED",
                    "epoch": 2,
                    "epochs": 2,
                    "metrics": {"mAP50": 0.9},
                }
            ),
            encoding="utf-8",
        )
        return Spawned(FakeProcess(0))

    execute_job(db_session, job, store=training_store, spawn=spawn)

    db_session.expire_all()
    stored = db_session.get(TrainingJob, job.id)
    assert stored is not None
    assert stored.status == TrainingJobStatus.SUCCEEDED
    assert stored.progress == 100
    model = db_session.exec(select(ModelArtifact)).one()
    assert model.active is False
    assert model.manifest["metrics"]["mAP50"] == 0.9
    assert (training_store.root / model.onnx_key).is_file()


def test_failed_job_records_the_error(
    db_session, training_store: TrainingStore, now: datetime
) -> None:
    job = make_job(db_session, training_store, now)

    def spawn(run) -> Spawned:
        run.log_path.write_text("CUDA out of memory", encoding="utf-8")
        return Spawned(FakeProcess(1))

    execute_job(db_session, job, store=training_store, spawn=spawn)

    db_session.expire_all()
    stored = db_session.get(TrainingJob, job.id)
    assert stored is not None
    assert stored.status == TrainingJobStatus.FAILED
    assert "code 1" in (stored.error or "")
    assert db_session.exec(select(ModelArtifact)).all() == []
