from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class HealthStatus(StrEnum):
    """Unified health vocabulary (baseline §13.1)."""

    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    MISCONFIGURED = "MISCONFIGURED"
    STOPPED = "STOPPED"


# One vocabulary for every health surface; the aliases keep call sites readable
# without letting runtime, camera, and platform states drift apart.
RuntimeStatus = HealthStatus
CameraHealthStatus = HealthStatus


class _RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CameraStatus(_RuntimeModel):
    camera_id: str
    status: CameraHealthStatus
    last_frame_at: AwareDatetime | None = None
    fps: float = Field(default=0.0, ge=0.0)
    inference_ms: float = Field(default=0.0, ge=0.0)
    dropped_frames: int = Field(default=0, ge=0)
    error: str | None = None


class RuntimeRegistration(_RuntimeModel):
    runtime_id: str
    base_url: str
    preview_base_url: str | None = None
    version: str
    camera_ids: tuple[str, ...] = ()


class RuntimeHeartbeat(_RuntimeModel):
    status: RuntimeStatus
    metrics: dict[str, float] = Field(default_factory=dict)
    cameras: tuple[CameraStatus, ...] = ()
