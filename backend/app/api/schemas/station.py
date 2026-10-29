from datetime import datetime
from enum import StrEnum

from contracts.enums import AlarmSeverity, CameraRole
from contracts.runtime import HealthStatus
from pydantic import BaseModel

from app.api.schemas.camera import CameraRead
from app.api.schemas.execution import ExecutionSummaryRead, StepSummaryRead


class ProcessStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    ALARM = "ALARM"
    COMPLETED = "COMPLETED"
    OFFLINE = "OFFLINE"


class StationCreate(BaseModel):
    code: str
    name: str
    zone: str | None = None


class StationRead(BaseModel):
    id: str
    code: str
    name: str
    zone: str | None
    created_at: datetime


class StationDetailRead(StationRead):
    cameras: list[CameraRead]


class CameraBindRequest(BaseModel):
    camera_id: str
    role: CameraRole


class StationCameraBindingRead(BaseModel):
    id: str
    station_id: str
    camera_id: str
    role: CameraRole
    valid_from: datetime
    valid_to: datetime | None


class StationRuntimeStateRead(BaseModel):
    station: StationRead
    camera: CameraRead | None
    execution: ExecutionSummaryRead | None
    steps: list[StepSummaryRead]
    process_status: ProcessStatus
    attention_since: datetime | None
    open_alarm_count: int
    highest_alarm_severity: AlarmSeverity | None
    health: HealthStatus
    preview_url: str | None
    snapshot_url: str | None
    last_frame_at: datetime | None
    server_time: datetime
