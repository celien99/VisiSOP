from dataclasses import dataclass
from typing import Protocol

from video_runtime.frame import Frame


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


class InferenceBackend(Protocol):
    def infer(self, frame: Frame) -> list[Detection]: ...

    def close(self) -> None: ...
