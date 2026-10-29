import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from contracts.runtime import HealthStatus

from video_runtime.frame import Frame
from video_runtime.sources.base import SourceHealth


class FileSource:
    """Replays a video file as paced BGR8 frames."""

    def __init__(
        self,
        path: Path,
        *,
        camera_id: str,
        fps: float = 10.0,
        loop: bool = True,
    ) -> None:
        self._path = Path(path)
        self._camera_id = camera_id
        self._fps = fps
        self._loop = loop
        self._capture: Any = None
        self._frame_seq = 0
        self._last_frame_at: datetime | None = None
        self._error: str | None = None
        self._next_at = 0.0

    def start(self) -> None:
        self._frame_seq = 0
        self._last_frame_at = None
        self._error = None
        capture = cv2.VideoCapture(str(self._path))
        if not capture.isOpened():
            capture.release()
            self._capture = None
            self._error = f"cannot open video source: {self._path}"
            return
        self._capture = capture
        self._next_at = time.monotonic()

    def read(self) -> Frame | None:
        if self._capture is None:
            return None
        self._pace()
        ok, image = self._capture.read()
        if not ok and self._loop:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, image = self._capture.read()
        if not ok:
            self._release()
            return None
        return self._frame(image)

    def stop(self) -> None:
        self._release()

    def health(self) -> SourceHealth:
        if self._error is not None:
            return SourceHealth(
                status=HealthStatus.UNAVAILABLE,
                last_frame_at=self._last_frame_at,
                error=self._error,
            )
        if self._capture is None:
            return SourceHealth(HealthStatus.STOPPED, last_frame_at=self._last_frame_at)
        if self._last_frame_at is None:
            return SourceHealth(HealthStatus.STARTING)
        return SourceHealth(HealthStatus.HEALTHY, last_frame_at=self._last_frame_at)

    def _pace(self) -> None:
        delay = self._next_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._next_at = time.monotonic() + 1.0 / self._fps

    def _frame(self, image: np.ndarray[Any, Any]) -> Frame:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        height, width = image.shape[:2]
        captured_at = datetime.now(UTC)
        frame = Frame(
            camera_id=self._camera_id,
            frame_seq=self._frame_seq,
            captured_at=captured_at,
            width=width,
            height=height,
            pixel_format="BGR8",
            data=image,
        )
        self._frame_seq += 1
        self._last_frame_at = captured_at
        return frame

    def _release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
