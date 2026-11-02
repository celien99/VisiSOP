from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import SessionDep
from app.api.schemas.training import (
    ActivationRequest,
    ActiveModelRead,
    AnnotationRead,
    AnnotationsUpdate,
    DatasetCreate,
    DatasetRead,
    ExtractRequest,
    FrameRead,
    JobCreate,
    JobRead,
    ModelRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    StatsRead,
    VideoRead,
)
from app.application import training_service
from app.core.config import settings
from app.infrastructure.training_store import TrainingStore
from app.models import (
    DatasetVersion,
    ModelArtifact,
    TrainingAnnotation,
    TrainingFrame,
    TrainingJob,
    TrainingProject,
    TrainingVideo,
)

router = APIRouter(prefix="/training", tags=["training"])

_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def _now() -> datetime:
    return datetime.now(UTC)


def _store() -> TrainingStore:
    return TrainingStore(settings.TRAINING_DIR)


def _project_read(project: TrainingProject) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        key=project.key,
        name=project.name,
        classes=list(project.classes),
        created_at=project.created_at,
    )


def _video_read(video: TrainingVideo) -> VideoRead:
    return VideoRead(
        id=video.id,
        project_id=video.project_id,
        filename=video.filename,
        status=video.status,
        duration_ms=video.duration_ms,
        fps=video.fps,
        frame_count=video.frame_count,
        error=video.error,
        created_at=video.created_at,
    )


def _frame_read(frame: TrainingFrame, count: int) -> FrameRead:
    return FrameRead(
        id=frame.id,
        video_id=frame.video_id,
        frame_index=frame.frame_index,
        timestamp_ms=frame.timestamp_ms,
        width=frame.width,
        height=frame.height,
        image_url=f"/api/training/frames/{frame.id}",
        thumb_url=f"/api/training/frames/{frame.id}/thumb",
        annotation_count=count,
    )


def _annotation_read(annotation: TrainingAnnotation) -> AnnotationRead:
    return AnnotationRead(
        id=annotation.id,
        frame_id=annotation.frame_id,
        class_name=annotation.class_name,
        x1=annotation.x1,
        y1=annotation.y1,
        x2=annotation.x2,
        y2=annotation.y2,
    )


def _dataset_read(dataset: DatasetVersion) -> DatasetRead:
    return DatasetRead(
        id=dataset.id,
        version=dataset.version,
        frame_count=dataset.frame_count,
        train_count=dataset.train_count,
        val_count=dataset.val_count,
        storage_key=dataset.storage_key,
        created_at=dataset.created_at,
    )


def _job_read(job: TrainingJob) -> JobRead:
    return JobRead(
        id=job.id,
        project_id=job.project_id,
        dataset_version_id=job.dataset_version_id,
        status=job.status,
        progress=job.progress,
        epochs=job.epochs,
        metrics=dict(job.metrics),
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _model_read(model: ModelArtifact) -> ModelRead:
    return ModelRead(
        id=model.id,
        project_id=model.project_id,
        version=model.version,
        training_job_id=model.training_job_id,
        metrics=dict(model.manifest.get("metrics", {})),
        manifest=dict(model.manifest),
        active=model.active,
        created_at=model.created_at,
        artifact_url=f"/api/training/models/{model.id}/artifact",
        names_url=f"/api/training/models/{model.id}/names",
    )


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, training_service.TrainingNotFound):
        return HTTPException(status_code=404, detail="not found")
    if isinstance(exc, training_service.TrainingConflict):
        return HTTPException(status_code=409, detail=str(exc) or "conflict")
    return HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/projects", response_model=list[ProjectRead], name="list_training_projects"
)
def list_training_projects(session: SessionDep) -> list[ProjectRead]:
    return [_project_read(item) for item in training_service.list_projects(session)]


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=201,
    name="create_training_project",
)
def create_training_project(payload: ProjectCreate, session: SessionDep) -> ProjectRead:
    try:
        project = training_service.create_project(
            session,
            key=payload.key,
            name=payload.name,
            classes=payload.classes,
            now=_now(),
        )
    except training_service.TrainingConflict:
        raise HTTPException(
            status_code=409, detail="project key already exists"
        ) from None
    except training_service.TrainingInvalid as exc:
        raise _http(exc) from None
    session.commit()
    return _project_read(project)


@router.get(
    "/projects/{project_id}", response_model=ProjectRead, name="get_training_project"
)
def get_training_project(project_id: str, session: SessionDep) -> ProjectRead:
    try:
        return _project_read(training_service.get_project(session, project_id))
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectRead,
    name="update_training_project",
)
def update_training_project(
    project_id: str, payload: ProjectUpdate, session: SessionDep
) -> ProjectRead:
    try:
        project = training_service.update_project(
            session,
            project_id=project_id,
            name=payload.name,
            classes=payload.classes,
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    except training_service.TrainingInvalid as exc:
        raise _http(exc) from None
    session.commit()
    return _project_read(project)


@router.post(
    "/projects/{project_id}/videos",
    response_model=VideoRead,
    status_code=201,
    name="upload_training_video",
)
async def upload_training_video(
    project_id: str,
    session: SessionDep,
    file: UploadFile = File(...),
) -> VideoRead:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in _VIDEO_SUFFIXES:
        raise HTTPException(status_code=415, detail=f"unsupported video type: {suffix}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty upload")
    if len(data) > settings.MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="video too large")
    try:
        video = training_service.add_video(
            session,
            _store(),
            project_id=project_id,
            filename=filename,
            suffix=suffix,
            data=data,
            now=_now(),
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    session.commit()
    return _video_read(video)


@router.get(
    "/projects/{project_id}/videos",
    response_model=list[VideoRead],
    name="list_training_videos",
)
def list_training_videos(project_id: str, session: SessionDep) -> list[VideoRead]:
    try:
        return [
            _video_read(video)
            for video in training_service.list_videos(session, project_id)
        ]
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@router.post(
    "/videos/{video_id}/extract",
    response_model=list[FrameRead],
    name="extract_training_video",
)
def extract_training_video(
    video_id: str, payload: ExtractRequest, session: SessionDep
) -> list[FrameRead]:
    try:
        frames = training_service.extract_video(
            session,
            _store(),
            video_id=video_id,
            fps=payload.fps,
            max_frames=payload.max_frames,
            now=_now(),
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="video not found") from None
    except training_service.TrainingConflict as exc:
        raise _http(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    session.commit()
    return [_frame_read(frame, 0) for frame in frames]


@router.delete("/videos/{video_id}", status_code=204, name="delete_training_video")
def delete_training_video(video_id: str, session: SessionDep) -> None:
    try:
        training_service.delete_video(session, _store(), video_id=video_id)
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="video not found") from None
    session.commit()


@router.get(
    "/videos/{video_id}/frames",
    response_model=list[FrameRead],
    name="list_training_frames",
)
def list_training_frames(video_id: str, session: SessionDep) -> list[FrameRead]:
    try:
        return [
            _frame_read(frame, count)
            for frame, count in training_service.list_frames(session, video_id)
        ]
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="video not found") from None


def _frame_file(frame_id: str, session: SessionDep, *, thumb: bool) -> FileResponse:
    try:
        frame = training_service.get_frame(session, frame_id)
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="frame not found") from None
    path = _store().resolve(frame.thumb_key if thumb else frame.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="frame file missing")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/frames/{frame_id}", name="get_training_frame")
def get_training_frame(frame_id: str, session: SessionDep) -> FileResponse:
    return _frame_file(frame_id, session, thumb=False)


@router.get("/frames/{frame_id}/thumb", name="get_training_frame_thumb")
def get_training_frame_thumb(frame_id: str, session: SessionDep) -> FileResponse:
    return _frame_file(frame_id, session, thumb=True)


@router.get(
    "/frames/{frame_id}/annotations",
    response_model=list[AnnotationRead],
    name="list_frame_annotations",
)
def list_frame_annotations(frame_id: str, session: SessionDep) -> list[AnnotationRead]:
    try:
        return [
            _annotation_read(item)
            for item in training_service.frame_annotations(session, frame_id)
        ]
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="frame not found") from None


@router.put(
    "/frames/{frame_id}/annotations",
    response_model=list[AnnotationRead],
    name="replace_frame_annotations",
)
def replace_frame_annotations(
    frame_id: str, payload: AnnotationsUpdate, session: SessionDep
) -> list[AnnotationRead]:
    try:
        annotations = training_service.replace_annotations(
            session,
            frame_id=frame_id,
            boxes=[item.model_dump() for item in payload.annotations],
            now=_now(),
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="frame not found") from None
    except training_service.TrainingInvalid as exc:
        raise _http(exc) from None
    session.commit()
    return [_annotation_read(item) for item in annotations]


@router.get(
    "/projects/{project_id}/stats", response_model=StatsRead, name="get_training_stats"
)
def get_training_stats(project_id: str, session: SessionDep) -> StatsRead:
    try:
        return StatsRead(**training_service.project_stats(session, project_id))
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetRead,
    status_code=201,
    name="create_training_dataset",
)
def create_training_dataset(
    project_id: str, payload: DatasetCreate, session: SessionDep
) -> DatasetRead:
    try:
        dataset = training_service.create_dataset(
            session,
            _store(),
            project_id=project_id,
            val_ratio=payload.val_ratio,
            now=_now(),
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    except training_service.TrainingInvalid as exc:
        raise _http(exc) from None
    session.commit()
    return _dataset_read(dataset)


@router.get(
    "/projects/{project_id}/datasets",
    response_model=list[DatasetRead],
    name="list_training_datasets",
)
def list_training_datasets(project_id: str, session: SessionDep) -> list[DatasetRead]:
    try:
        return [
            _dataset_read(item)
            for item in training_service.list_datasets(session, project_id)
        ]
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobRead,
    status_code=201,
    name="create_training_job",
)
def create_training_job(
    project_id: str, payload: JobCreate, session: SessionDep
) -> JobRead:
    try:
        job = training_service.create_job(
            session,
            project_id=project_id,
            dataset_version_id=payload.dataset_version_id,
            epochs=payload.epochs,
            now=_now(),
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="not found") from None
    except training_service.TrainingConflict as exc:
        raise _http(exc) from None
    except training_service.TrainingInvalid as exc:
        raise _http(exc) from None
    session.commit()
    return _job_read(job)


@router.get(
    "/projects/{project_id}/jobs",
    response_model=list[JobRead],
    name="list_training_jobs",
)
def list_training_jobs(project_id: str, session: SessionDep) -> list[JobRead]:
    try:
        return [
            _job_read(job) for job in training_service.list_jobs(session, project_id)
        ]
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@router.get("/jobs/{job_id}", response_model=JobRead, name="get_training_job")
def get_training_job(job_id: str, session: SessionDep) -> JobRead:
    try:
        return _job_read(training_service.get_job(session, job_id))
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="job not found") from None


@router.get(
    "/projects/{project_id}/models",
    response_model=list[ModelRead],
    name="list_training_models",
)
def list_training_models(project_id: str, session: SessionDep) -> list[ModelRead]:
    try:
        return [
            _model_read(model)
            for model in training_service.list_models(session, project_id)
        ]
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None


@router.post(
    "/models/{model_id}/activate",
    response_model=ModelRead,
    name="activate_training_model",
)
def activate_training_model(
    model_id: str, payload: ActivationRequest, session: SessionDep
) -> ModelRead:
    try:
        model = training_service.activate_model(
            session, model_id=model_id, actor=payload.operator, now=_now()
        )
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="model not found") from None
    except training_service.TrainingInvalid as exc:
        raise _http(exc) from None
    session.commit()
    return _model_read(model)


@router.get(
    "/projects/{project_key}/active-model",
    response_model=ActiveModelRead,
    name="get_active_model",
)
def get_active_model(project_key: str, session: SessionDep) -> ActiveModelRead:
    try:
        found = training_service.active_model(session, project_key)
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="project not found") from None
    if found is None:
        raise HTTPException(status_code=404, detail="no active model")
    project, model = found
    # The model artifact pins its own class names; project edits after
    # training must not rewrite what the ONNX actually outputs.
    classes = list(model.manifest.get("names", [])) or list(project.classes)
    return ActiveModelRead(
        id=model.id,
        project_key=project.key,
        version=model.version,
        classes=classes,
        metrics=dict(model.manifest.get("metrics", {})),
        onnx_url=f"/api/training/models/{model.id}/artifact",
        names_url=f"/api/training/models/{model.id}/names",
    )


def _model_file(model_id: str, session: SessionDep, *, names: bool) -> FileResponse:
    try:
        model = training_service.get_model(session, model_id)
    except training_service.TrainingNotFound:
        raise HTTPException(status_code=404, detail="model not found") from None
    onnx_path, names_path = _store().model_paths(model.id)
    path = names_path if names else onnx_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="model file missing")
    media = "text/plain" if names else "application/octet-stream"
    return FileResponse(path, media_type=media)


@router.get("/models/{model_id}/artifact", name="download_model_artifact")
def download_model_artifact(model_id: str, session: SessionDep) -> FileResponse:
    return _model_file(model_id, session, names=False)


@router.get("/models/{model_id}/names", name="download_model_names")
def download_model_names(model_id: str, session: SessionDep) -> FileResponse:
    return _model_file(model_id, session, names=True)
