from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import RuntimeClientFactoryDep, SessionDep
from app.api.schemas.camera import (
    CameraCommandRead,
    CameraCreate,
    CameraHealthRead,
    CameraRead,
    CameraUpdate,
)
from app.application import station_service
from app.infrastructure.runtime_client import RuntimeUnavailable

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[CameraRead], name="list_cameras")
def list_cameras(session: SessionDep) -> list[CameraRead]:
    return station_service.list_cameras(session, now=_now())


@router.post("", response_model=CameraRead, status_code=201, name="create_camera")
def create_camera(payload: CameraCreate, session: SessionDep) -> CameraRead:
    try:
        camera = station_service.create_camera(
            session,
            code=payload.code,
            name=payload.name,
            runtime_id=payload.runtime_id,
            source_type=payload.source_type,
            source_config=payload.source_config,
            preview_url=payload.preview_url,
            snapshot_url=payload.snapshot_url,
            now=_now(),
        )
    except station_service.CameraCodeConflict:
        raise HTTPException(
            status_code=409, detail="camera code already exists"
        ) from None
    session.commit()
    session.refresh(camera)
    return station_service.camera_read(camera, _now())


@router.patch("/{camera_id}", response_model=CameraRead, name="update_camera")
def update_camera(
    camera_id: str, payload: CameraUpdate, session: SessionDep
) -> CameraRead:
    try:
        camera = station_service.update_camera(
            session,
            camera_id=camera_id,
            changes=payload.model_dump(exclude_unset=True),
            now=_now(),
        )
    except station_service.CameraNotFound:
        raise HTTPException(status_code=404, detail="camera not found") from None
    session.commit()
    session.refresh(camera)
    return station_service.camera_read(camera, _now())


def _command(
    camera_id: str,
    command: str,
    session: SessionDep,
    client_factory: RuntimeClientFactoryDep,
) -> CameraCommandRead:
    try:
        return station_service.send_camera_command(
            session,
            camera_id=camera_id,
            command=command,
            client_factory=client_factory,
            now=_now(),
        )
    except station_service.CameraNotFound:
        raise HTTPException(status_code=404, detail="camera not found") from None
    except RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post(
    "/{camera_id}/start", response_model=CameraCommandRead, name="start_camera"
)
def start_camera(
    camera_id: str,
    session: SessionDep,
    client_factory: RuntimeClientFactoryDep,
) -> CameraCommandRead:
    return _command(camera_id, "start", session, client_factory)


@router.post("/{camera_id}/stop", response_model=CameraCommandRead, name="stop_camera")
def stop_camera(
    camera_id: str,
    session: SessionDep,
    client_factory: RuntimeClientFactoryDep,
) -> CameraCommandRead:
    return _command(camera_id, "stop", session, client_factory)


@router.get(
    "/{camera_id}/health", response_model=CameraHealthRead, name="get_camera_health"
)
def get_camera_health(camera_id: str, session: SessionDep) -> CameraHealthRead:
    try:
        return station_service.camera_health(session, camera_id=camera_id, now=_now())
    except station_service.CameraNotFound:
        raise HTTPException(status_code=404, detail="camera not found") from None
