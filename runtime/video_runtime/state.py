import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from contracts.events import VisionEvent
from contracts.runtime import CameraStatus, HealthStatus

from video_runtime.frame import Frame
from video_runtime.perception import BBox, Perception

OverlayMode = Literal["off", "boxes", "all"]

_JPEG_QUALITY = 85
_BOX_COLOUR = (0, 255, 0)
_REGION_COLOUR = (255, 191, 0)


@dataclass
class RuntimeState:
    """Latest frame, overlay preview, perception, and health for the server."""

    runtime_id: str
    start_callback: Callable[[], None] | None = None
    stop_callback: Callable[[], None] | None = None
    preview_fps: int = 10
    overlay: OverlayMode = "all"
    regions: tuple[tuple[BBox, str], ...] = ()
    status: HealthStatus = HealthStatus.STARTING
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    _latest: dict[str, Frame] = field(default_factory=dict, init=False, repr=False)
    _jpeg: dict[str, bytes] = field(default_factory=dict, init=False, repr=False)
    _perception: dict[str, Perception] = field(
        default_factory=dict, init=False, repr=False
    )
    _events: dict[str, tuple[VisionEvent, ...]] = field(
        default_factory=dict, init=False, repr=False
    )
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def set_perception(
        self, perception: Perception, events: Sequence[VisionEvent] = ()
    ) -> None:
        frame = perception.frame
        image = _draw(frame.data, perception, self.overlay, self.regions)
        ok, encoded = cv2.imencode(
            ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
        )
        with self._lock:
            self._latest[frame.camera_id] = frame
            self._perception[frame.camera_id] = perception
            self._events[frame.camera_id] = tuple(events)
            if ok:
                self._jpeg[frame.camera_id] = encoded.tobytes()

    def latest(self, camera_id: str) -> Frame | None:
        with self._lock:
            return self._latest.get(camera_id)

    def jpeg(self, camera_id: str) -> bytes | None:
        with self._lock:
            return self._jpeg.get(camera_id)

    def perception(self, camera_id: str) -> Perception | None:
        with self._lock:
            return self._perception.get(camera_id)

    def events(self, camera_id: str) -> tuple[VisionEvent, ...]:
        with self._lock:
            return self._events.get(camera_id, ())

    def cameras(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._latest))

    def camera_status(self, camera_id: str) -> CameraStatus:
        frame = self.latest(camera_id)
        not_streaming = {
            HealthStatus.UNAVAILABLE,
            HealthStatus.STOPPED,
            HealthStatus.MISCONFIGURED,
        }
        if frame is None or self.status in not_streaming:
            return CameraStatus(
                camera_id=camera_id,
                status=HealthStatus.UNAVAILABLE,
                last_frame_at=None if frame is None else frame.captured_at,
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


def _draw(
    image: np.ndarray,
    perception: Perception,
    mode: OverlayMode,
    regions: Sequence[tuple[BBox, str]],
) -> np.ndarray:
    if mode == "off":
        return image
    canvas = image.copy()
    height, width = canvas.shape[:2]
    if mode == "all":
        for rect, label in regions:
            x1, y1, x2, y2 = _pixels(rect, width, height)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), _REGION_COLOUR, 1)
            cv2.putText(
                canvas,
                label,
                (x1 + 3, max(y1 - 4, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                _REGION_COLOUR,
                1,
            )
    for detection in perception.detections:
        x1, y1, x2, y2 = _pixels(detection.bbox, width, height)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), _BOX_COLOUR, 2)
        track = perception.track_for(detection)
        suffix = f" #{track.track_id.rsplit(':', 1)[-1]}" if track else ""
        cv2.putText(
            canvas,
            f"{detection.class_name} {detection.confidence:.2f}{suffix}",
            (x1 + 3, max(y1 - 4, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            _BOX_COLOUR,
            1,
        )
    return canvas


def _pixels(rect: BBox, width: int, height: int) -> tuple[int, int, int, int]:
    return (
        round(rect[0] * width),
        round(rect[1] * height),
        round(rect[2] * width),
        round(rect[3] * height),
    )
