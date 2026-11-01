import httpx
import pytest
from conftest import make_event
from contracts.enums import CameraRole
from pydantic import ValidationError

from video_runtime.config import (
    BackendConfig,
    BindingConfig,
    CameraConfig,
    FileSourceConfig,
    ModelConfig,
    RuntimeConfig,
)
from video_runtime.main import _heartbeat, preflight
from video_runtime.publisher import HttpEventPublisher
from video_runtime.state import RuntimeState


def make_config(tmp_path) -> RuntimeConfig:
    return RuntimeConfig(
        runtime_id="runtime-01",
        station_id="st-01",
        camera=CameraConfig(
            camera_id="cam-01",
            role=CameraRole.OVERVIEW,
            source=FileSourceConfig(path=tmp_path / "clip.mp4"),
        ),
        backend=BackendConfig(base_url="http://api/api"),
        model=ModelConfig(
            onnx_path=tmp_path / "model.onnx",
            class_names_path=tmp_path / "coco.names",
        ),
        evidence_dir=tmp_path,
    )


def test_heartbeat_surfaces_publisher_queue_health(tmp_path) -> None:
    publisher = HttpEventPublisher(
        "http://api/api",
        retries=0,
        backoff_ms=(0,),
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    publisher.publish(make_event())

    beat = _heartbeat(
        make_config(tmp_path), RuntimeState(runtime_id="runtime-01"), publisher
    )

    assert beat.metrics["events_pending"] == 1.0
    assert beat.metrics["events_failed"] == 1.0
    assert [camera.camera_id for camera in beat.cameras] == ["cam-01"]


def binding(**overrides) -> BindingConfig:
    values = {
        "event_type": "bottle_in_pickup_zone",
        "primitive": "object_in_zone",
        "params": {
            "object_class": "bottle",
            "zone": "pickup",
            "rect": (0.0, 0.0, 0.5, 1.0),
        },
    }
    values.update(overrides)
    return BindingConfig(**values)


def test_preflight_accepts_the_demo_bindings(tmp_path) -> None:
    config = make_config(tmp_path)
    config.bindings = [binding()]
    preflight(config, ["bottle", "person"])


def test_binding_rejects_an_unregistered_event_type() -> None:
    with pytest.raises(ValidationError, match="not_registered"):
        binding(event_type="not_registered")


def test_preflight_rejects_a_class_the_model_does_not_know(tmp_path) -> None:
    config = make_config(tmp_path)
    config.bindings = [
        binding(
            params={
                "object_class": "human",
                "zone": "pickup",
                "rect": (0.0, 0.0, 0.5, 1.0),
            }
        )
    ]
    with pytest.raises(SystemExit, match="human"):
        preflight(config, ["bottle"])
