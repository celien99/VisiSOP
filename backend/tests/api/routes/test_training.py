from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.infrastructure.training_store import TrainingStore
from app.models import ModelArtifact


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


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/training/projects",
        json={"key": "remote", "name": "Remote", "classes": ["remote", "battery"]},
    )
    assert response.status_code == 201
    return response.json()


def _upload(client: TestClient, project_id: str, clip: Path) -> dict:
    response = client.post(
        f"/api/training/projects/{project_id}/videos",
        files={"file": ("clip.avi", clip.read_bytes(), "video/x-msvideo")},
    )
    assert response.status_code == 201
    return response.json()


def test_training_flow_and_model_activation(
    client: TestClient,
    training_store: TrainingStore,
    clip: Path,
    db_session,
    now: datetime,
) -> None:
    project = _project(client)
    video = _upload(client, project["id"], clip)
    assert video["status"] == "UPLOADED"

    extracted = client.post(
        f"/api/training/videos/{video['id']}/extract", json={"fps": 5}
    )
    assert extracted.status_code == 200
    frames = extracted.json()
    assert len(frames) == 30

    for frame in frames[:5]:
        response = client.put(
            f"/api/training/frames/{frame['id']}/annotations",
            json={
                "annotations": [
                    {
                        "class_name": "remote",
                        "x1": 0.1,
                        "y1": 0.1,
                        "x2": 0.5,
                        "y2": 0.5,
                    }
                ]
            },
        )
        assert response.status_code == 200

    stats = client.get(f"/api/training/projects/{project['id']}/stats").json()
    assert stats["labeled_frames"] == 5

    dataset = client.post(
        f"/api/training/projects/{project['id']}/datasets", json={"val_ratio": 0.2}
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    job = client.post(
        f"/api/training/projects/{project['id']}/jobs",
        json={"dataset_version_id": dataset_id, "epochs": 5},
    )
    assert job.status_code == 201
    assert job.json()["status"] == "QUEUED"

    model_id = str(uuid4())
    onnx_path, names_path = training_store.model_paths(model_id)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    onnx_path.write_bytes(b"onnx")
    names_path.write_text("remote\nbattery\n", encoding="utf-8", newline="\n")
    db_session.add(
        ModelArtifact(
            id=model_id,
            project_id=project["id"],
            training_job_id=job.json()["id"],
            version=1,
            onnx_key=f"models/{model_id}/best.onnx",
            names_key=f"models/{model_id}/names.txt",
            manifest={"metrics": {"mAP50": 0.9}},
            active=False,
            created_at=now,
        )
    )
    db_session.flush()

    activated = client.post(
        f"/api/training/models/{model_id}/activate", json={"operator": "tester"}
    )
    assert activated.status_code == 200
    assert activated.json()["active"] is True

    active = client.get("/api/training/projects/remote/active-model")
    assert active.status_code == 200
    body = active.json()
    assert body["id"] == model_id
    assert body["classes"] == ["remote", "battery"]
    assert client.get(body["onnx_url"]).content == b"onnx"
    assert client.get(body["names_url"]).text == "remote\nbattery\n"


def test_upload_rejects_unsupported_types(
    client: TestClient, training_store: TrainingStore
) -> None:
    project = _project(client)
    response = client.post(
        f"/api/training/projects/{project['id']}/videos",
        files={"file": ("clip.txt", b"x", "text/plain")},
    )
    assert response.status_code == 415


def test_annotations_reject_a_class_outside_the_project(
    client: TestClient, training_store: TrainingStore, clip: Path
) -> None:
    project = _project(client)
    video = _upload(client, project["id"], clip)
    frames = client.post(
        f"/api/training/videos/{video['id']}/extract", json={"fps": 5}
    ).json()
    response = client.put(
        f"/api/training/frames/{frames[0]['id']}/annotations",
        json={
            "annotations": [
                {"class_name": "human", "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}
            ]
        },
    )
    assert response.status_code == 422
