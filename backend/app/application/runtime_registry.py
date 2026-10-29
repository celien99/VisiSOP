from dataclasses import dataclass, field
from datetime import datetime

from contracts.runtime import (
    CameraStatus,
    HealthStatus,
    RuntimeHeartbeat,
    RuntimeRegistration,
)

from app.api.schemas.runtime import RuntimeRead
from app.core.config import settings


class RuntimeNotFound(LookupError):
    pass


@dataclass
class RuntimeEntry:
    registration: RuntimeRegistration
    last_heartbeat_at: datetime
    status: HealthStatus = HealthStatus.STARTING
    cameras: dict[str, CameraStatus] = field(default_factory=dict)


class RuntimeRegistry:
    # shortcut: in-memory registry; persist/lease when multiple API workers.
    def __init__(self) -> None:
        self._entries: dict[str, RuntimeEntry] = {}

    def clear(self) -> None:
        self._entries.clear()

    def register(
        self, registration: RuntimeRegistration, now: datetime
    ) -> RuntimeEntry:
        entry = RuntimeEntry(
            registration=registration,
            last_heartbeat_at=now,
            status=HealthStatus.STARTING,
        )
        self._entries[registration.runtime_id] = entry
        return entry

    def heartbeat(
        self, runtime_id: str, beat: RuntimeHeartbeat, now: datetime
    ) -> RuntimeEntry:
        entry = self._entries.get(runtime_id)
        if entry is None:
            raise RuntimeNotFound(runtime_id)
        entry.last_heartbeat_at = now
        entry.status = beat.status
        entry.cameras = {camera.camera_id: camera for camera in beat.cameras}
        return entry

    def get(self, runtime_id: str) -> RuntimeEntry | None:
        return self._entries.get(runtime_id)

    def entries(self) -> list[RuntimeEntry]:
        return [self._entries[key] for key in sorted(self._entries)]

    def is_stale(self, entry: RuntimeEntry, now: datetime) -> bool:
        elapsed_ms = (now - entry.last_heartbeat_at).total_seconds() * 1000
        return elapsed_ms > settings.RUNTIME_STALE_AFTER_MS

    def status(self, entry: RuntimeEntry, now: datetime) -> HealthStatus:
        if self.is_stale(entry, now):
            return HealthStatus.UNAVAILABLE
        return entry.status

    def camera(self, camera_id: str, now: datetime) -> CameraStatus | None:
        for entry in self.entries():
            status = entry.cameras.get(camera_id)
            if status is None:
                continue
            if self.is_stale(entry, now):
                return status.model_copy(update={"status": HealthStatus.UNAVAILABLE})
            return status
        return None

    def read(self, entry: RuntimeEntry, now: datetime) -> RuntimeRead:
        return RuntimeRead(
            runtime_id=entry.registration.runtime_id,
            base_url=entry.registration.base_url,
            preview_base_url=entry.registration.preview_base_url,
            version=entry.registration.version,
            camera_ids=list(entry.registration.camera_ids),
            status=self.status(entry, now),
            last_heartbeat_at=entry.last_heartbeat_at,
        )

    def read_all(self, now: datetime) -> list[RuntimeRead]:
        return [self.read(entry, now) for entry in self.entries()]


runtime_registry = RuntimeRegistry()
