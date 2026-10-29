from datetime import datetime

from fastapi.testclient import TestClient

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
