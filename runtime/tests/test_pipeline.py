import time
from datetime import timedelta

from conftest import T, make_detection, make_frame
from contracts.runtime import HealthStatus

from video_runtime.config import ZoneConfig
from video_runtime.event_builder import EventBuilder
from video_runtime.evidence import EvidenceWriter
from video_runtime.inference.base import Detection
from video_runtime.pipeline import Pipeline
from video_runtime.publisher import PublishOutcome
from video_runtime.sources.base import SourceHealth
from video_runtime.sources.fake import FakeSource
from video_runtime.state import RuntimeState
from video_runtime.zones import ZoneMapper

PICKUP = ZoneConfig(
    name="pickup",
    rect=(0.0, 0.0, 0.5, 1.0),
    classes=["bottle"],
    event_type="bottle_in_pickup_zone",
)


class FakeInference:
    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections

    def infer(self, frame: object) -> list[Detection]:
        return self._detections

    def close(self) -> None:
        pass


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> PublishOutcome:
        self.events.append(event)
        return PublishOutcome(
            delivered=True, duplicate=False, status_code=202, error=None
        )

    def flush(self) -> int:
        return 0


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
    )
    publisher = publisher or RecordingPublisher()
    state = RuntimeState(runtime_id="runtime-01")
    pipeline = Pipeline(
        FakeSource([]),
        FakeInference(detections),
        ZoneMapper([PICKUP]),
        builder,
        publisher,
        state,
    )
    return pipeline, publisher, state


def test_process_frame_emits_zone_event_and_updates_preview(tmp_path) -> None:
    pipeline, publisher, state = make_pipeline(tmp_path)
    events = pipeline.process_frame(make_frame(seq=1), now=T)
    assert [event.event_type for event in events] == ["bottle_in_pickup_zone"]
    assert publisher.events == events
    assert state.latest("cam-01") is not None
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
        "st-01", "cam-01", "overview", "yolo11n-coco", "1", EvidenceWriter(tmp_path)
    )
    pipeline = Pipeline(
        InfiniteSource(),
        TimedInference([]),
        ZoneMapper([PICKUP]),
        builder,
        RecordingPublisher(),
        RuntimeState(runtime_id="runtime-01"),
        inference_interval_ms=100,
    )
    holder["pipeline"] = pipeline
    pipeline.run()
    assert len(calls) == 3
    assert calls[-1] - calls[0] >= 0.18
