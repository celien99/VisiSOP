from datetime import datetime
from typing import Any
from uuid import uuid4

from contracts.enums import (
    AlarmCategory,
    AlarmSeverity,
    AlarmStatus,
    CameraRole,
    ReasonCode,
)
from contracts.runtime import HealthStatus
from sqlmodel import Session, col, select

from app.api.schemas.camera import CameraCommandRead, CameraHealthRead, CameraRead
from app.api.schemas.execution import ExecutionSummaryRead, StepSummaryRead
from app.api.schemas.station import (
    CameraBindRequest,
    ProcessStatus,
    StationCameraBindingRead,
    StationDetailRead,
    StationRead,
    StationRuntimeStateRead,
)
from app.application.alarm_service import alarm_dedup_key, upsert_alarm
from app.application.audit import write_audit
from app.application.runtime_registry import runtime_registry
from app.application.sop_service import ordered_step_definitions
from app.domain.sop.model import ExecutionStatus, StepStatus
from app.infrastructure.runtime_client import RuntimeClientFactory, RuntimeUnavailable
from app.models import (
    Alarm,
    Camera,
    SOPDefinition,
    SOPExecution,
    SOPVersion,
    Station,
    StationCameraBinding,
    StepExecution,
)

_ACTIVE_EXECUTION_STATUSES = (
    ExecutionStatus.RUNNING,
    ExecutionStatus.PAUSED,
    ExecutionStatus.NEEDS_REVIEW,
)
_OPEN_ALARM_STATUSES = (AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED)
_SEVERITY_RANK = {
    AlarmSeverity.LOW: 1,
    AlarmSeverity.MEDIUM: 2,
    AlarmSeverity.HIGH: 3,
    AlarmSeverity.CRITICAL: 4,
}


class StationNotFound(LookupError):
    pass


class CameraNotFound(LookupError):
    pass


class StationCodeConflict(ValueError):
    pass


class CameraCodeConflict(ValueError):
    pass


class CameraAlreadyBound(ValueError):
    pass


def station_read(station: Station) -> StationRead:
    return StationRead(
        id=station.id,
        code=station.code,
        name=station.name,
        zone=station.zone,
        created_at=station.created_at,
    )


def camera_read(camera: Camera, now: datetime) -> CameraRead:
    status = runtime_registry.camera(camera.id, now)
    return CameraRead(
        id=camera.id,
        code=camera.code,
        name=camera.name,
        runtime_id=camera.runtime_id,
        source_type=camera.source_type,
        preview_url=camera.preview_url,
        snapshot_url=camera.snapshot_url,
        health=status.status if status is not None else HealthStatus.UNKNOWN,
        last_frame_at=status.last_frame_at if status is not None else None,
        created_at=camera.created_at,
    )


def _station(session: Session, station_id: str) -> Station:
    station = session.get(Station, station_id)
    if station is None:
        raise StationNotFound(station_id)
    return station


def _camera(session: Session, camera_id: str) -> Camera:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise CameraNotFound(camera_id)
    return camera


def _active_bindings(
    session: Session, *, station_id: str | None = None, camera_id: str | None = None
) -> list[StationCameraBinding]:
    statement = select(StationCameraBinding).where(
        col(StationCameraBinding.valid_to).is_(None)
    )
    if station_id is not None:
        statement = statement.where(col(StationCameraBinding.station_id) == station_id)
    if camera_id is not None:
        statement = statement.where(col(StationCameraBinding.camera_id) == camera_id)
    statement = statement.order_by(col(StationCameraBinding.valid_from).desc())
    return list(session.exec(statement).all())


def _bound_camera(session: Session, station_id: str) -> Camera | None:
    for binding in _active_bindings(session, station_id=station_id):
        camera = session.get(Camera, binding.camera_id)
        if camera is not None:
            return camera
    return None


def create_station(
    session: Session, *, code: str, name: str, zone: str | None, now: datetime
) -> Station:
    existing = session.exec(select(Station).where(Station.code == code)).first()
    if existing is not None:
        raise StationCodeConflict(code)
    station = Station(id=str(uuid4()), code=code, name=name, zone=zone, created_at=now)
    session.add(station)
    write_audit(
        session,
        actor="system",
        action="station.created",
        object_type="station",
        object_id=station.id,
        detail={"code": code},
        now=now,
    )
    return station


def list_stations(session: Session) -> list[StationRead]:
    stations = session.exec(select(Station).order_by(Station.code)).all()
    return [station_read(station) for station in stations]


def get_station(
    session: Session, *, station_id: str, now: datetime
) -> StationDetailRead:
    station = _station(session, station_id)
    cameras = [
        camera_read(camera, now)
        for camera in (
            session.get(Camera, binding.camera_id)
            for binding in _active_bindings(session, station_id=station_id)
        )
        if camera is not None
    ]
    return StationDetailRead(**station_read(station).model_dump(), cameras=cameras)


def bind_camera(
    session: Session,
    *,
    station_id: str,
    request: CameraBindRequest,
    now: datetime,
) -> StationCameraBindingRead:
    _station(session, station_id)
    _camera(session, request.camera_id)
    existing = _active_bindings(session, camera_id=request.camera_id)
    for binding in existing:
        if binding.station_id == station_id:
            return StationCameraBindingRead(
                id=binding.id,
                station_id=binding.station_id,
                camera_id=binding.camera_id,
                role=CameraRole(binding.role),
                valid_from=binding.valid_from,
                valid_to=binding.valid_to,
            )
        raise CameraAlreadyBound(request.camera_id)

    binding = StationCameraBinding(
        id=str(uuid4()),
        station_id=station_id,
        camera_id=request.camera_id,
        role=request.role,
        valid_from=now,
    )
    session.add(binding)
    write_audit(
        session,
        actor="system",
        action="station.camera_bound",
        object_type="station",
        object_id=station_id,
        detail={
            "camera_id": request.camera_id,
            "role": request.role.value,
        },
        now=now,
    )
    return StationCameraBindingRead(
        id=binding.id,
        station_id=binding.station_id,
        camera_id=binding.camera_id,
        role=CameraRole(binding.role),
        valid_from=binding.valid_from,
        valid_to=binding.valid_to,
    )


def create_camera(
    session: Session,
    *,
    code: str,
    name: str,
    runtime_id: str,
    source_type: str,
    source_config: dict[str, Any],
    preview_url: str | None,
    snapshot_url: str | None,
    now: datetime,
) -> Camera:
    existing = session.exec(select(Camera).where(Camera.code == code)).first()
    if existing is not None:
        raise CameraCodeConflict(code)
    camera = Camera(
        id=str(uuid4()),
        code=code,
        name=name,
        runtime_id=runtime_id,
        source_type=source_type,
        source_config=source_config,
        preview_url=preview_url,
        snapshot_url=snapshot_url,
        created_at=now,
    )
    session.add(camera)
    write_audit(
        session,
        actor="system",
        action="camera.created",
        object_type="camera",
        object_id=camera.id,
        detail={"code": code, "runtime_id": runtime_id},
        now=now,
    )
    return camera


def update_camera(
    session: Session, *, camera_id: str, changes: dict[str, Any], now: datetime
) -> Camera:
    camera = _camera(session, camera_id)
    for field, value in changes.items():
        setattr(camera, field, value)
    session.add(camera)
    write_audit(
        session,
        actor="system",
        action="camera.updated",
        object_type="camera",
        object_id=camera.id,
        detail={"fields": sorted(changes)},
        now=now,
    )
    return camera


def list_cameras(session: Session, *, now: datetime) -> list[CameraRead]:
    cameras = session.exec(select(Camera).order_by(Camera.code)).all()
    return [camera_read(camera, now) for camera in cameras]


def camera_health(
    session: Session, *, camera_id: str, now: datetime
) -> CameraHealthRead:
    camera = _camera(session, camera_id)
    status = runtime_registry.camera(camera.id, now)
    if status is None:
        return CameraHealthRead(
            camera_id=camera.id,
            status=HealthStatus.UNKNOWN,
            last_frame_at=None,
            fps=None,
            inference_ms=None,
            dropped_frames=None,
            error=None,
        )
    return CameraHealthRead(
        camera_id=status.camera_id,
        status=status.status,
        last_frame_at=status.last_frame_at,
        fps=status.fps,
        inference_ms=status.inference_ms,
        dropped_frames=status.dropped_frames,
        error=status.error,
    )


def _record_command_failure(
    session: Session,
    camera: Camera,
    command: str,
    error: RuntimeUnavailable,
    now: datetime,
) -> None:
    station_id = next(
        (
            binding.station_id
            for binding in _active_bindings(session, camera_id=camera.id)
        ),
        None,
    )
    if station_id is not None:
        category = AlarmCategory.DEVICE_HEALTH
        upsert_alarm(
            session,
            dedup_key=alarm_dedup_key(
                category=category, station_id=station_id, camera_id=camera.id
            ),
            category=category,
            severity=AlarmSeverity.HIGH,
            reason_code=None,
            execution_id=None,
            station_id=station_id,
            camera_id=camera.id,
            step_key=None,
            source_event_id=None,
            message=f"camera {command} failed: {error}",
            now=now,
        )
    write_audit(
        session,
        actor="system",
        action=f"camera.{command}_failed",
        object_type="camera",
        object_id=camera.id,
        detail={"error": str(error)},
        now=now,
    )
    session.commit()


def send_camera_command(
    session: Session,
    *,
    camera_id: str,
    command: str,
    client_factory: RuntimeClientFactory,
    now: datetime,
) -> CameraCommandRead:
    camera = _camera(session, camera_id)
    entry = runtime_registry.get(camera.runtime_id)
    if entry is None:
        unavailable = RuntimeUnavailable(
            f"runtime {camera.runtime_id} is not registered"
        )
        _record_command_failure(session, camera, command, unavailable, now)
        raise unavailable

    try:
        with client_factory(entry.registration.base_url) as client:
            if command == "start":
                client.start_camera(camera.id)
            else:
                client.stop_camera(camera.id)
    except RuntimeUnavailable as exc:
        _record_command_failure(session, camera, command, exc, now)
        raise

    write_audit(
        session,
        actor="system",
        action=f"camera.{command}_requested",
        object_type="camera",
        object_id=camera.id,
        detail={"runtime_id": camera.runtime_id},
        now=now,
    )
    session.commit()
    return CameraCommandRead(camera_id=camera.id, command=command)


def _current_execution(session: Session, station_id: str) -> SOPExecution | None:
    statement = (
        select(SOPExecution)
        .where(SOPExecution.station_id == station_id)
        .order_by(col(SOPExecution.started_at).desc())
    )
    executions = list(session.exec(statement).all())
    for execution in executions:
        if execution.status in _ACTIVE_EXECUTION_STATUSES:
            return execution
    return executions[0] if executions else None


def execution_summary_for(
    session: Session, execution: SOPExecution
) -> tuple[ExecutionSummaryRead, list[StepSummaryRead], list[StepExecution]]:
    version = session.get(SOPVersion, execution.sop_version_id)
    definition = (
        session.get(SOPDefinition, version.sop_id) if version is not None else None
    )
    step_rows = list(
        session.exec(
            select(StepExecution).where(StepExecution.execution_id == execution.id)
        ).all()
    )
    by_key = {row.step_key: row for row in step_rows}
    steps: list[StepSummaryRead] = []
    if version is not None:
        for definition_row in ordered_step_definitions(session, version):
            row = by_key.get(definition_row.step_key)
            if row is None:
                continue
            steps.append(
                StepSummaryRead(
                    key=definition_row.step_key,
                    name=definition_row.name,
                    status=StepStatus(row.status),
                    reason_code=ReasonCode(row.reason_code)
                    if row.reason_code
                    else None,
                    started_at=row.activated_at,
                )
            )

    priority = (
        StepStatus.ACTIVE,
        StepStatus.NEEDS_REVIEW,
        StepStatus.TIMED_OUT,
        StepStatus.FAILED,
    )
    current = next(
        (step for wanted in priority for step in steps if step.status == wanted),
        None,
    )
    summary = ExecutionSummaryRead(
        id=execution.id,
        sop_key=definition.key if definition is not None else "",
        sop_version=version.version if version is not None else 0,
        status=ExecutionStatus(execution.status),
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        current_step_key=current.key if current is not None else None,
        current_step_name=current.name if current is not None else None,
        current_step_status=current.status if current is not None else None,
    )
    return summary, steps, step_rows


def _open_alarms(session: Session, station_id: str) -> list[Alarm]:
    statement = select(Alarm).where(
        Alarm.station_id == station_id,
        col(Alarm.status).in_(_OPEN_ALARM_STATUSES),
    )
    return list(session.exec(statement).all())


def _highest_severity(alarms: list[Alarm]) -> AlarmSeverity | None:
    severities = [AlarmSeverity(alarm.severity) for alarm in alarms]
    if not severities:
        return None
    return max(severities, key=lambda severity: _SEVERITY_RANK[severity])


def _process_status(
    camera: CameraRead | None,
    execution: SOPExecution | None,
    alarms: list[Alarm],
) -> ProcessStatus:
    if camera is None or camera.health == HealthStatus.UNAVAILABLE:
        return ProcessStatus.OFFLINE
    if (
        execution is not None
        and ExecutionStatus(execution.status) == ExecutionStatus.NEEDS_REVIEW
    ):
        return ProcessStatus.REVIEW
    if alarms:
        return ProcessStatus.ALARM
    if execution is None:
        return ProcessStatus.IDLE
    status = ExecutionStatus(execution.status)
    if status in (ExecutionStatus.RUNNING, ExecutionStatus.PAUSED):
        return ProcessStatus.RUNNING
    if status == ExecutionStatus.COMPLETED:
        return ProcessStatus.COMPLETED
    return ProcessStatus.IDLE


def _attention_since(
    process_status: ProcessStatus,
    step_rows: list[StepExecution],
    alarms: list[Alarm],
) -> datetime | None:
    if process_status == ProcessStatus.REVIEW:
        times = [
            row.updated_at for row in step_rows if row.status == StepStatus.NEEDS_REVIEW
        ]
        return min(times) if times else None
    if process_status == ProcessStatus.ALARM:
        return min(alarm.first_seen_at for alarm in alarms) if alarms else None
    return None


def _state_for_station(
    session: Session, station: Station, now: datetime
) -> StationRuntimeStateRead:
    camera = _bound_camera(session, station.id)
    camera_view = camera_read(camera, now) if camera is not None else None
    execution = _current_execution(session, station.id)
    if execution is None:
        summary: ExecutionSummaryRead | None = None
        steps: list[StepSummaryRead] = []
        step_rows: list[StepExecution] = []
    else:
        summary, steps, step_rows = execution_summary_for(session, execution)
    alarms = _open_alarms(session, station.id)
    process_status = _process_status(camera_view, execution, alarms)
    return StationRuntimeStateRead(
        station=station_read(station),
        camera=camera_view,
        execution=summary,
        steps=steps,
        process_status=process_status,
        attention_since=_attention_since(process_status, step_rows, alarms),
        open_alarm_count=len(alarms),
        highest_alarm_severity=_highest_severity(alarms),
        health=camera_view.health
        if camera_view is not None
        else HealthStatus.UNAVAILABLE,
        preview_url=camera.preview_url if camera is not None else None,
        snapshot_url=camera.snapshot_url if camera is not None else None,
        last_frame_at=camera_view.last_frame_at if camera_view is not None else None,
        server_time=now,
    )


def station_runtime_state(
    session: Session, *, station_id: str, now: datetime
) -> StationRuntimeStateRead:
    return _state_for_station(session, _station(session, station_id), now)


def list_station_runtime_states(
    session: Session, *, now: datetime
) -> list[StationRuntimeStateRead]:
    stations = session.exec(select(Station).order_by(Station.code)).all()
    return [_state_for_station(session, station, now) for station in stations]
