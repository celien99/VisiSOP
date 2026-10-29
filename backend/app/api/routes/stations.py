from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas.station import (
    CameraBindRequest,
    StationCameraBindingRead,
    StationCreate,
    StationDetailRead,
    StationRead,
    StationRuntimeStateRead,
)
from app.application import station_service

router = APIRouter(prefix="/stations", tags=["stations"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=list[StationRead], name="list_stations")
def list_stations(session: SessionDep) -> list[StationRead]:
    return station_service.list_stations(session)


@router.post("", response_model=StationRead, status_code=201, name="create_station")
def create_station(payload: StationCreate, session: SessionDep) -> StationRead:
    try:
        station = station_service.create_station(
            session,
            code=payload.code,
            name=payload.name,
            zone=payload.zone,
            now=_now(),
        )
    except station_service.StationCodeConflict:
        raise HTTPException(
            status_code=409, detail="station code already exists"
        ) from None
    session.commit()
    session.refresh(station)
    return station_service.station_read(station)


# Declared before /{station_id} so the literal path wins.
@router.get(
    "/runtime-state",
    response_model=list[StationRuntimeStateRead],
    name="list_station_runtime_states",
)
def list_station_runtime_states(
    session: SessionDep,
) -> list[StationRuntimeStateRead]:
    return station_service.list_station_runtime_states(session, now=_now())


@router.get("/{station_id}", response_model=StationDetailRead, name="get_station")
def get_station(station_id: str, session: SessionDep) -> StationDetailRead:
    try:
        return station_service.get_station(session, station_id=station_id, now=_now())
    except station_service.StationNotFound:
        raise HTTPException(status_code=404, detail="station not found") from None


@router.get(
    "/{station_id}/runtime-state",
    response_model=StationRuntimeStateRead,
    name="get_station_runtime_state",
)
def get_station_runtime_state(
    station_id: str, session: SessionDep
) -> StationRuntimeStateRead:
    try:
        return station_service.station_runtime_state(
            session, station_id=station_id, now=_now()
        )
    except station_service.StationNotFound:
        raise HTTPException(status_code=404, detail="station not found") from None


@router.post(
    "/{station_id}/cameras",
    response_model=StationCameraBindingRead,
    status_code=201,
    name="bind_station_camera",
)
def bind_station_camera(
    station_id: str, payload: CameraBindRequest, session: SessionDep
) -> StationCameraBindingRead:
    try:
        binding = station_service.bind_camera(
            session, station_id=station_id, request=payload, now=_now()
        )
    except station_service.StationNotFound:
        raise HTTPException(status_code=404, detail="station not found") from None
    except station_service.CameraNotFound:
        raise HTTPException(status_code=404, detail="camera not found") from None
    except station_service.CameraAlreadyBound:
        raise HTTPException(
            status_code=409, detail="camera is already bound to another station"
        ) from None
    session.commit()
    return binding
