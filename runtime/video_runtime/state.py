import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
from contracts.runtime import CameraStatus, HealthStatus

from video_runtime.frame import Frame

_JPEG_QUALITY = 85


@dataclass
class RuntimeState:
    """Latest frame, encoded preview, and health for the HTTP server."""

    runtime_id: str
    start_callback: Callable[[], None] | None = None
    stop_callback: Callable[[], None] | None = None
    preview_fps: int = 10
    status: HealthStatus = HealthStatus.STARTING
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    _latest: dict[str, Frame] = field(default_factory=dict, init=False, repr=False)
    _jpeg: dict[str, bytes] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def set_frame(self, frame: Frame) -> None:
        ok, encoded = cv2.imencode(
            ".jpg", frame.data, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
        )
        with self._lock:
            self._latest[frame.camera_id] = frame
            if ok:
                self._jpeg[frame.camera_id] = encoded.tobytes()

    def latest(self, camera_id: str) -> Frame | None:
        with self._lock:
            return self._latest.get(camera_id)

    def jpeg(self, camera_id: str) -> bytes | None:
        with self._lock:
            return self._jpeg.get(camera_id)

    def cameras(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._latest))

    def camera_status(self, camera_id: str) -> CameraStatus:
        frame = self.latest(camera_id)
        if frame is None or self.status is HealthStatus.UNAVAILABLE:
            return CameraStatus(
                camera_id=camera_id,
                status=HealthStatus.UNAVAILABLE,
                error=self.error or "no frame yet",
            )
        return CameraStatus(
            camera_id=camera_id,
            status=HealthStatus.HEALTHY,
            last_frame_at=frame.captured_at,
            fps=self.metrics.get("fps", 0.0),
            inference_ms=self.metrics.get("inference_ms", 0.0),
            dropped_frames=int(self.metrics.get("dropped_frames", 0.0)),
        )

    def start(self) -> None:
        if self.start_callback is not None:
            self.start_callback()

    def stop(self) -> None:
        if self.stop_callback is not None:
            self.stop_callback()
