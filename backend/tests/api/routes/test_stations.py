from datetime import datetime

from fastapi.testclient import TestClient

from app.api.deps import get_runtime_client_factory
from app.api.schemas.execution import ExecutionDetailRead
from app.main import app
from app.models import Station


def test_runtime_state_is_idle_before_an_execution(
    client: TestClient, seeded_station: Station
) -> None:
    body = client.get("/api/stations/runtime-state").json()
    assert len(body) == 1
    assert body[0]["process_status"] == "IDLE"
    assert body[0]["steps"] == []
    assert body[0]["station"]["id"] == "st-01"


def test_bulk_runtime_state_path_wins_over_station_lookup(
    client: TestClient, seeded_station: Station
) -> None:
    response = client.get("/api/stations/runtime-state")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert client.get("/api/stations/st-01/runtime-state").status_code == 200


def test_camera_start_returns_503_when_runtime_is_down(
    client: TestClient, seeded_station: Station
) -> None:
    response = client.post("/api/cameras/cam-01/start")
    assert response.status_code == 503
    assert "runtime" in response.json()["detail"].lower()


def test_heartbeat_turns_camera_healthy(
    client: TestClient, seeded_station: Station, now: datetime
) -> None:
    registered = client.post(
        "/api/runtimes/register",
        json={
            "runtime_id": "runtime-01",
            "base_url": "http://127.0.0.1:8001",
            "preview_base_url": "http://127.0.0.1:8001",
            "version": "0.1.0",
            "camera_ids": ["cam-01"],
        },
    )
    assert registered.status_code == 200

    beat = client.post(
        "/api/runtimes/runtime-01/heartbeat",
        json={
            "status": "HEALTHY",
            "metrics": {"fps": 9.8},
            "cameras": [
                {
                    "camera_id": "cam-01",
                    "status": "HEALTHY",
                    "last_frame_at": now.isoformat(),
                    "fps": 9.8,
                    "inference_ms": 42.0,
                    "dropped_frames": 0,
                    "error": None,
                }
            ],
        },
    )
    assert beat.status_code == 200

    health = client.get("/api/cameras/cam-01/health").json()
    assert health["status"] == "HEALTHY"
    assert health["last_frame_at"] is not None


def test_station_detail_and_creation_paths(
    client: TestClient, seeded_station: Station
) -> None:
    detail = client.get("/api/stations/st-01").json()
    assert detail["cameras"][0]["id"] == "cam-01"
    assert client.get("/api/stations/nope").status_code == 404
    assert (
        client.post("/api/stations", json={"code": "ST-01", "name": "dup"}).status_code
        == 409
    )
    assert (
        client.post("/api/stations", json={"code": "ST-02", "name": "二"}).status_code
        == 201
    )
    bound = client.post(
        "/api/stations/st-01/cameras",
        json={"camera_id": "cam-01", "role": "overview"},
    )
    assert bound.status_code == 201
    assert (
        client.post(
            "/api/stations/st-01/cameras",
            json={"camera_id": "nope", "role": "overview"},
        ).status_code
        == 404
    )


def test_runtime_state_with_active_execution(
    client: TestClient, active_execution: ExecutionDetailRead
) -> None:
    body = client.get("/api/stations/st-01/runtime-state").json()
    assert body["process_status"] == "RUNNING"
    assert body["execution"]["current_step_key"] == "pick_bottle"
    assert [step["key"] for step in body["steps"]] == [
        "pick_bottle",
        "place_bottle",
        "verify_placement",
    ]


def test_camera_paths_and_command_forwarding(
    client: TestClient, seeded_station: Station
) -> None:
    created = client.post(
        "/api/cameras",
        json={
            "code": "CAM-02",
            "name": "第二相机",
            "runtime_id": "runtime-01",
            "source_type": "gige",
        },
    )
    assert created.status_code == 201
    assert "source_config" not in created.json()
    camera_id = created.json()["id"]
    patched = client.patch(f"/api/cameras/{camera_id}", json={"name": "新名称"})
    assert patched.status_code == 200
    assert (
        client.patch("/api/cameras/nope", json={"name": "x"}).status_code == 404
    )

    client.post(
        "/api/runtimes/register",
        json={
            "runtime_id": "runtime-01",
            "base_url": "http://127.0.0.1:8001",
            "version": "0.1.0",
            "camera_ids": ["cam-01"],
        },
    )
    calls: list[tuple[str, str]] = []

    class StubClient:
        def __enter__(self) -> "StubClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def start_camera(self, camera_id: str) -> None:
            calls.append(("start", camera_id))

        def stop_camera(self, camera_id: str) -> None:
            calls.append(("stop", camera_id))

    app.dependency_overrides[get_runtime_client_factory] = lambda: (
        lambda base_url: StubClient()
    )
    assert client.post("/api/cameras/cam-01/start").status_code == 200
    assert client.post("/api/cameras/cam-01/stop").status_code == 200
    assert calls == [("start", "cam-01"), ("stop", "cam-01")]
