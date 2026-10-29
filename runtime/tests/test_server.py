from conftest import make_frame
from contracts.runtime import CameraHealthStatus, RuntimeStatus
from fastapi.testclient import TestClient

from video_runtime.server import create_app
from video_runtime.state import RuntimeState


def test_health_snapshot_and_stream() -> None:
    state = RuntimeState(runtime_id="runtime-01")
    state.set_frame(make_frame(seq=1))
    client = TestClient(create_app(state))

    body = client.get("/health").json()
    assert body["runtime_id"] == "runtime-01"
    assert body["cameras"][0]["camera_id"] == "cam-01"
    assert body["cameras"][0]["last_frame_at"].startswith("2026-01-01T12:00")

    snapshot = client.get("/snapshot/cam-01")
    assert snapshot.status_code == 200
    assert snapshot.headers["content-type"] == "image/jpeg"

    stream = client.get("/stream/cam-01?max_chunks=2")
    assert stream.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert stream.content.count(b"--frame") == 2


def test_snapshot_without_a_frame_is_404() -> None:
    client = TestClient(create_app(RuntimeState(runtime_id="runtime-01")))
    assert client.get("/snapshot/cam-09").status_code == 404


def test_start_stop_calls_the_state() -> None:
    calls: list[str] = []
    state = RuntimeState(
        runtime_id="runtime-01",
        start_callback=lambda: calls.append("start"),
        stop_callback=lambda: calls.append("stop"),
    )
    client = TestClient(create_app(state))
    assert client.post("/cameras/cam-01/start").status_code == 200
    assert client.post("/cameras/cam-01/stop").status_code == 200
    assert calls == ["start", "stop"]


def test_stream_for_an_unknown_camera_is_404() -> None:
    client = TestClient(create_app(RuntimeState(runtime_id="runtime-01")))
    assert client.get("/stream/cam-09?max_chunks=1").status_code == 404


def test_camera_status_reports_a_stopped_source_as_unavailable() -> None:
    state = RuntimeState(runtime_id="runtime-01")
    state.set_frame(make_frame(seq=1))
    state.status = RuntimeStatus.STOPPED
    state.error = "source stopped"
    status = state.camera_status("cam-01")
    assert status.status == CameraHealthStatus.UNAVAILABLE
    assert status.error == "source stopped"
