from datetime import datetime

from contracts.runtime import RuntimeRegistration

from app.application.runtime_registry import runtime_registry
from app.application.station_service import camera_read
from app.models import Camera


def _camera(*, preview_url: str | None = None) -> Camera:
    return Camera(
        id="cam-01",
        code="CAM-01",
        name="主相机",
        runtime_id="runtime-01",
        source_type="mvs",
        source_config={},
        preview_url=preview_url,
        snapshot_url=None,
        created_at=datetime(2026, 1, 1),
    )


def _registration(*camera_ids: str) -> RuntimeRegistration:
    return RuntimeRegistration(
        runtime_id="runtime-01",
        base_url="http://127.0.0.1:8001",
        preview_base_url="http://127.0.0.1:8001",
        version="0.1.0",
        camera_ids=camera_ids,
    )


def test_camera_read_falls_back_to_the_stored_urls(now: datetime) -> None:
    camera = _camera(preview_url="http://example.test/stream/cam-01")

    read = camera_read(camera, now)

    assert read.preview_url == "http://example.test/stream/cam-01"
    assert read.snapshot_url is None


def test_camera_read_derives_urls_from_the_registered_runtime(now: datetime) -> None:
    runtime_registry.register(_registration("cam-01"), now)

    read = camera_read(_camera(), now)

    assert read.preview_url == "http://127.0.0.1:8001/stream/cam-01"
    assert read.snapshot_url == "http://127.0.0.1:8001/snapshot/cam-01"


def test_camera_read_ignores_a_runtime_that_does_not_own_the_camera(
    now: datetime,
) -> None:
    runtime_registry.register(_registration("cam-02"), now)
    camera = _camera(preview_url="http://example.test/stream/cam-01")

    read = camera_read(camera, now)

    assert read.preview_url == "http://example.test/stream/cam-01"
