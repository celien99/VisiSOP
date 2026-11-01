import threading
import time
from datetime import timedelta

import cv2
from conftest import T, make_detection, make_frame
from contracts.events import ModelRef
from contracts.runtime import HealthStatus

from video_runtime.config import BindingConfig
from video_runtime.event_builder import EventBuilder, binding_from_config
from video_runtime.evidence import EvidenceWriter
from video_runtime.inference.base import Detection
from video_runtime.perception import IoUTracker
from video_runtime.pipeline import Pipeline
from video_runtime.publisher import PublishOutcome
from video_runtime.sources.base import SourceHealth
from video_runtime.sources.fake import FakeSource
from video_runtime.sources.file import FileSource
from video_runtime.state import RuntimeState


def make_binding():
    return binding_from_config(
        BindingConfig(
            event_type="bottle_in_pickup_zone",
            primitive="object_in_zone",
            params={
                "object_class": "bottle",
                "zone": "pickup",
                "rect": (0.0, 0.0, 0.5, 1.0),
                "min_conf": 0.25,
            },
        )
    )


class FakeInference:
    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections
        self.closed = False

    def infer(self, frame: object) -> list[Detection]:
        return self._detections

    def current_ref(self) -> ModelRef:
        return ModelRef(name="test-model", version="1")

    def classes(self) -> tuple[str, ...]:
        return ("bottle",)

    def close(self) -> None:
        self.closed = True


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.closed = False

    def publish(self, event: object) -> PublishOutcome:
        self.events.append(event)
        return PublishOutcome(
            delivered=True, duplicate=False, status_code=202, error=None
        )

    def flush(self) -> int:
        return 0

    def close(self) -> None:
        self.closed = True


def make_pipeline(
    tmp_path,
    detections: list[Detection] | None = None,
    publisher: RecordingPublisher | None = None,
) -> tuple[Pipeline, RecordingPublisher, RuntimeState]:
    if detections is None:
        detections = [make_detection(bbox=(0.1, 0.1, 0.3, 0.3))]
    builder = EventBuilder(
        "st-01",
        "cam-01",
        "overview",
        "yolo11n-coco",
        "1",
        EvidenceWriter(tmp_path),
        bindings=[make_binding()],
    )
    publisher = publisher or RecordingPublisher()
    state = RuntimeState(runtime_id="runtime-01")
    pipeline = Pipeline(
        FakeSource([]),
        FakeInference(detections),
        IoUTracker(),
        builder,
        publisher,
        state,
    )
    return pipeline, publisher, state


def test_process_frame_emits_primitive_event_and_updates_preview(tmp_path) -> None:
    pipeline, publisher, state = make_pipeline(tmp_path)
    events = pipeline.process_frame(make_frame(seq=1), now=T)
    assert [event.event_type for event in events] == ["bottle_in_pickup_zone"]
    assert publisher.events == events
    assert state.latest("cam-01") is not None
    assert state.perception("cam-01") is not None
    assert "inference_ms" in state.metrics
    second = pipeline.process_frame(
        make_frame(seq=2, at=T + timedelta(milliseconds=100)),
        now=T + timedelta(milliseconds=100),
    )
    assert second == []


def test_no_detection_produces_no_event(tmp_path) -> None:
    pipeline, _, state = make_pipeline(tmp_path, detections=[])
    assert pipeline.process_frame(make_frame(seq=1), now=T) == []
    assert state.latest("cam-01") is not None


class InfiniteSource:
    def __init__(self) -> None:
        self.seq = 0

    def start(self) -> None:
        pass

    def read(self):
        self.seq += 1
        return make_frame(seq=self.seq, at=T + timedelta(milliseconds=100 * self.seq))

    def stop(self) -> None:
        pass

    def health(self) -> SourceHealth:
        return SourceHealth(HealthStatus.HEALTHY)


def test_preview_updates_before_the_event_is_published(tmp_path) -> None:
    class WatchPublisher(RecordingPublisher):
        def __init__(self) -> None:
            super().__init__()
            self.state: RuntimeState | None = None
            self.preview_ready: list[bool] = []

        def publish(self, event: object) -> PublishOutcome:
            assert self.state is not None
            self.preview_ready.append(self.state.latest("cam-01") is not None)
            return super().publish(event)

    watch = WatchPublisher()
    pipeline, _, state = make_pipeline(tmp_path, publisher=watch)
    watch.state = state
    pipeline.process_frame(make_frame(seq=1), now=T)
    assert watch.preview_ready == [True]


def test_run_enforces_the_inference_interval(tmp_path) -> None:
    calls: list[float] = []
    holder: dict[str, Pipeline] = {}

    class TimedInference(FakeInference):
        def infer(self, frame: object) -> list[Detection]:
            calls.append(time.monotonic())
            if len(calls) == 3:
                holder["pipeline"].stop()
            return super().infer(frame)

    builder = EventBuilder(
        "st-01",
        "cam-01",
        "overview",
        "yolo11n-coco",
        "1",
        EvidenceWriter(tmp_path),
        bindings=[make_binding()],
    )
    pipeline = Pipeline(
        InfiniteSource(),
        TimedInference([]),
        IoUTracker(),
        builder,
        RecordingPublisher(),
        RuntimeState(runtime_id="runtime-01"),
        inference_interval_ms=100,
    )
    holder["pipeline"] = pipeline
    pipeline.run()
    assert len(calls) == 3
    assert calls[-1] - calls[0] >= 0.18


def test_run_exits_when_a_finite_source_ends(tmp_path) -> None:
    path = tmp_path / "one.avi"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 100.0, (64, 48)
    )
    writer.write(make_frame().data)
    writer.release()

    builder = EventBuilder(
        "st-01",
        "cam-01",
        "overview",
        "yolo11n-coco",
        "1",
        EvidenceWriter(tmp_path),
        bindings=[make_binding()],
    )
    state = RuntimeState(runtime_id="runtime-01")
    pipeline = Pipeline(
        FileSource(path, camera_id="cam-01", fps=100.0, loop=False),
        FakeInference([]),
        IoUTracker(),
        builder,
        RecordingPublisher(),
        state,
    )
    thread = threading.Thread(target=pipeline.run, daemon=True)
    thread.start()
    thread.join(timeout=3)
    exited = not thread.is_alive()
    pipeline.stop()
    thread.join(timeout=1)
    assert exited
    assert state.status is HealthStatus.STOPPED


def test_close_releases_the_publisher_and_inference(tmp_path) -> None:
    pipeline, publisher, _ = make_pipeline(tmp_path)
    pipeline.close()
    assert publisher.closed is True
