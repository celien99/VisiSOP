from collections import deque
from collections.abc import Sequence

from contracts.runtime import HealthStatus

from video_runtime.frame import Frame
from video_runtime.sources.base import SourceHealth


class FakeSource:
    """Finite frame list for pipeline tests and smoke runs."""

    def __init__(self, frames: Sequence[Frame]) -> None:
        self._frames = deque(frames)

    def start(self) -> None:
        pass

    def read(self) -> Frame | None:
        return self._frames.popleft() if self._frames else None

    def stop(self) -> None:
        self._frames.clear()

    def health(self) -> SourceHealth:
        return SourceHealth(HealthStatus.HEALTHY)
