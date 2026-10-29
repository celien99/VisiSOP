import threading
from collections import deque

from video_runtime.frame import Frame


class FrameBuffer:
    """Bounded queue that keeps the newest frames and drops the oldest.

    Real-time detection only needs the latest frame, so a full buffer
    discards rather than blocking the capture thread.
    """

    def __init__(self, maxsize: int = 1) -> None:
        self._items: deque[Frame] = deque(maxlen=maxsize)
        self._dropped = 0
        self._condition = threading.Condition()

    @property
    def dropped(self) -> int:
        with self._condition:
            return self._dropped

    def put(self, frame: Frame) -> None:
        with self._condition:
            if len(self._items) == self._items.maxlen:
                self._dropped += 1
            self._items.append(frame)
            self._condition.notify()

    def get(self, timeout: float | None = None) -> Frame | None:
        with self._condition:
            if not self._items and not self._condition.wait_for(
                lambda: bool(self._items), timeout
            ):
                return None
            return self._items.popleft()

    def snapshot(self) -> Frame | None:
        with self._condition:
            return self._items[-1] if self._items else None
