from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from contracts.runtime import HealthStatus

from video_runtime.frame import Frame


@dataclass(frozen=True)
class SourceHealth:
    status: HealthStatus
    last_frame_at: datetime | None = None
    error: str | None = None


class VideoSource(Protocol):
    def start(self) -> None: ...

    def read(self) -> Frame | None: ...

    def stop(self) -> None: ...

    def health(self) -> SourceHealth: ...
