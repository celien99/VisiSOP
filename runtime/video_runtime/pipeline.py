import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from contracts.events import VisionEvent
from contracts.runtime import HealthStatus

from video_runtime.buffer import FrameBuffer
from video_runtime.event_builder import EventBuilder
from video_runtime.frame import Frame
from video_runtime.inference.base import InferenceBackend
from video_runtime.publisher import HttpEventPublisher
from video_runtime.sources.base import VideoSource
from video_runtime.state import RuntimeState
from video_runtime.zones import ZoneMapper


class Pipeline:
    """Captures frames, runs inference, emits events, and feeds the preview.

    The reader thread keeps the newest frame; the worker samples it at the
    inference interval. The publisher never raises, so a backend outage only
    grows the bounded retry queue.
    """

    def __init__(
        self,
        source: VideoSource,
        inference: InferenceBackend,
        zones: ZoneMapper,
        builder: EventBuilder,
        publisher: HttpEventPublisher,
        state: RuntimeState,
        *,
        inference_interval_ms: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._inference = inference
        self._zones = zones
        self._builder = builder
        self._publisher = publisher
        self._state = state
        self._interval_s = inference_interval_ms / 1000
        self._clock = clock
        self._buffer = FrameBuffer(maxsize=1)
        self._stop = threading.Event()
        self._last_captured_at: datetime | None = None

    def process_frame(self, frame: Frame, now: datetime) -> list[VisionEvent]:
        started = self._clock()
        detections = self._inference.infer(frame)
        inference_ms = (self._clock() - started) * 1000
        hits = self._zones.map(detections, frame)
        events = self._builder.build(frame, hits, now)
        # Preview and health update before publishing: a slow or down backend
        # must never freeze the live picture or report a stale camera.
        self._state.set_frame(frame)
        self._state.status = HealthStatus.HEALTHY
        self._state.metrics["inference_ms"] = inference_ms
        self._state.metrics["fps"] = self._fps(frame.captured_at)
        self._state.metrics["dropped_frames"] = float(self._buffer.dropped)
        self._last_captured_at = frame.captured_at
        for event in events:
            self._publisher.publish(event)
        return events

    def run(self) -> None:
        self._source.start()
        reader = threading.Thread(target=self._read_frames, daemon=True)
        reader.start()
        next_sample = self._clock()
        try:
            while not self._stop.is_set():
                frame = self._buffer.get(timeout=self._interval_s)
                if frame is None:
                    next_sample = self._clock()
                    continue
                self.process_frame(frame, datetime.now(UTC))
                self._publisher.flush()
                next_sample += self._interval_s
                now = self._clock()
                if next_sample < now:
                    next_sample = now  # a slow frame must not queue catch-up bursts
                self._stop.wait(next_sample - now)
        finally:
            self._source.stop()
            reader.join(timeout=1.0)

    def stop(self) -> None:
        self._stop.set()
        self._source.stop()

    def _read_frames(self) -> None:
        while not self._stop.is_set():
            frame = self._source.read()
            if frame is not None:
                self._buffer.put(frame)
                continue
            health = self._source.health()
            if health.status is HealthStatus.STOPPED:
                self._state.status = HealthStatus.STOPPED
                self._state.error = health.error or "source stopped"
                return
            if health.status is HealthStatus.UNAVAILABLE:
                self._state.status = HealthStatus.UNAVAILABLE
                self._state.error = health.error
            self._stop.wait(0.1)

    def _fps(self, captured_at: datetime) -> float:
        if self._last_captured_at is None:
            return 0.0
        delta = (captured_at - self._last_captured_at).total_seconds()
        return 1.0 / delta if delta > 0 else 0.0
