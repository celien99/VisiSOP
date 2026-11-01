"""Run queued training jobs in the runtime's 3.12 environment.

The API process never imports torch: this worker writes a job spec, spawns
`video_runtime.tools.train_yolo` through uv, mirrors progress, and stores the
resulting ONNX artifact. One job runs at a time.
"""

import asyncio
import json
import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Protocol
from uuid import uuid4

from sqlmodel import Session, col, func, select

from app.application import training_service
from app.core.config import settings
from app.core.db import engine
from app.infrastructure.training_store import TrainingStore
from app.models import (
    DatasetVersion,
    ModelArtifact,
    TrainingJob,
    TrainingJobStatus,
)

logger = logging.getLogger(__name__)


class TrainerProcess(Protocol):
    def poll(self) -> int | None: ...

    def wait(self) -> int: ...


@dataclass(frozen=True)
class Spawned:
    process: TrainerProcess
    log_handle: IO[bytes] | None = None


@dataclass(frozen=True)
class TrainingRun:
    job_id: str
    project_key: str
    model_id: str
    spec_path: Path
    log_path: Path
    progress_path: Path
    metrics_path: Path
    onnx_path: Path
    names_path: Path


Spawn = Callable[[TrainingRun], Spawned]


def _now() -> datetime:
    return datetime.now(UTC)


def _spawn(run: TrainingRun) -> Spawned:
    runtime_dir = Path(settings.RUNTIME_PROJECT_DIR).expanduser().resolve()
    handle = run.log_path.open("wb")
    command = [
        "uv",
        "run",
        "--project",
        str(runtime_dir),
        "--extra",
        "train",
        "python",
        "-m",
        "video_runtime.tools.train_yolo",
        "--job",
        str(run.spec_path),
    ]
    process = subprocess.Popen(
        command,
        cwd=str(runtime_dir),
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return Spawned(process=process, log_handle=handle)


def prepare_run(
    session: Session, job: TrainingJob, store: TrainingStore
) -> TrainingRun:
    project = training_service.get_project(session, job.project_id)
    dataset = session.get(DatasetVersion, job.dataset_version_id)
    if dataset is None:
        raise RuntimeError(f"dataset {job.dataset_version_id} is missing")
    data_yaml = str(dataset.manifest.get("data_yaml", ""))
    if not data_yaml:
        raise RuntimeError("dataset manifest has no data_yaml")
    model_id = str(uuid4())
    run_dir = store.job_dir(project.key, job.id)
    onnx_path, names_path = store.model_paths(model_id)
    run = TrainingRun(
        job_id=job.id,
        project_key=project.key,
        model_id=model_id,
        spec_path=run_dir / "job.json",
        log_path=run_dir / "train.log",
        progress_path=run_dir / "progress.json",
        metrics_path=run_dir / "metrics.json",
        onnx_path=onnx_path,
        names_path=names_path,
    )
    spec = {
        "job_id": job.id,
        "data_yaml": store.resolve(data_yaml).as_posix(),
        "output_dir": (run_dir / "run").as_posix(),
        "progress_path": run.progress_path.as_posix(),
        "metrics_path": run.metrics_path.as_posix(),
        "onnx_path": run.onnx_path.as_posix(),
        "names_path": run.names_path.as_posix(),
        "epochs": job.epochs,
        "imgsz": settings.TRAINING_IMGSZ,
        "device": settings.TRAINING_DEVICE,
        "base_model": settings.TRAINING_BASE_MODEL,
    }
    run.spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return run


def execute_job(
    session: Session,
    job: TrainingJob,
    *,
    store: TrainingStore | None = None,
    spawn: Spawn | None = None,
) -> None:
    store = store or TrainingStore(settings.TRAINING_DIR)
    spawn = spawn or _spawn
    run = prepare_run(session, job, store)
    job.status = TrainingJobStatus.RUNNING
    job.started_at = _now()
    job.progress = 0
    job.error = None
    session.add(job)
    session.commit()

    spawned = spawn(run)
    try:
        while spawned.process.poll() is None:
            _mirror_progress(session, job, run)
            time.sleep(max(0.05, settings.TRAINING_POLL_MS / 1000))
        code = spawned.process.wait()
    finally:
        if spawned.log_handle is not None:
            spawned.log_handle.close()

    _mirror_progress(session, job, run)
    if code == 0 and run.onnx_path.is_file() and run.names_path.is_file():
        _succeed(session, job, run, store)
    else:
        _fail(job, run, code)
    session.commit()


def _mirror_progress(session: Session, job: TrainingJob, run: TrainingRun) -> None:
    data = _read_json(run.progress_path)
    if not data:
        return
    epochs = int(data.get("epochs", job.epochs) or job.epochs)
    epoch = int(data.get("epoch", 0) or 0)
    progress = min(100, round(100 * epoch / max(1, epochs)))
    metrics = data.get("metrics")
    changed = False
    if progress != job.progress:
        job.progress = progress
        changed = True
    if isinstance(metrics, dict) and metrics:
        job.metrics = {str(key): float(value) for key, value in metrics.items()}
        changed = True
    error = data.get("error")
    if isinstance(error, str) and error:
        job.error = error
        changed = True
    if changed:
        session.add(job)
        session.commit()


def _succeed(
    session: Session, job: TrainingJob, run: TrainingRun, store: TrainingStore
) -> None:
    payload = _read_json(run.metrics_path)
    metrics = payload.get("metrics", {})
    names = payload.get("names", [])
    last = session.exec(
        select(func.max(ModelArtifact.version)).where(
            ModelArtifact.project_id == job.project_id
        )
    ).one()
    version = int(last or 0) + 1
    model = ModelArtifact(
        id=run.model_id,
        project_id=job.project_id,
        training_job_id=job.id,
        version=version,
        onnx_key=_relative(run.onnx_path, store),
        names_key=_relative(run.names_path, store),
        manifest={"metrics": metrics, "names": names, "epochs": job.epochs},
        active=False,
        created_at=_now(),
    )
    session.add(model)
    job.status = TrainingJobStatus.SUCCEEDED
    job.progress = 100
    job.metrics = metrics
    job.artifact_key = _relative(run.onnx_path, store)
    job.log_key = _relative(run.log_path, store)
    job.error = None
    job.finished_at = _now()


def _fail(job: TrainingJob, run: TrainingRun, code: int) -> None:
    job.status = TrainingJobStatus.FAILED
    job.finished_at = _now()
    if not job.error:
        job.error = f"trainer exited with code {code}"
    tail = _log_tail(run.log_path)
    if tail:
        job.error = f"{job.error}: {tail}"


def _relative(path: Path, store: TrainingStore) -> str:
    return path.resolve().relative_to(store.root).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _log_tail(path: Path, limit: int = 2000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def process_next_job() -> bool:
    with Session(engine) as session:
        job = session.exec(
            select(TrainingJob)
            .where(col(TrainingJob.status) == TrainingJobStatus.QUEUED)
            .order_by(col(TrainingJob.created_at))
        ).first()
        if job is None:
            return False
        execute_job(session, job)
        return True


async def run_training_worker() -> None:
    while True:
        try:
            worked = await asyncio.to_thread(process_next_job)
        except Exception:  # worker boundary: keep the loop alive
            logger.exception("training worker tick failed")
            worked = False
        if not worked:
            await asyncio.sleep(max(0.05, settings.TRAINING_POLL_MS / 1000))
