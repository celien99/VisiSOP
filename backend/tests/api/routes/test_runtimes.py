from fastapi.testclient import TestClient


def test_register_list_and_heartbeat(client: TestClient) -> None:
    registration = {
        "runtime_id": "runtime-01",
        "base_url": "http://127.0.0.1:8001",
        "preview_base_url": "http://127.0.0.1:8001",
        "version": "0.1.0",
        "camera_ids": ["cam-01"],
    }
    assert client.post("/api/runtimes/register", json=registration).status_code == 200
    listed = client.get("/api/runtimes").json()
    assert [runtime["runtime_id"] for runtime in listed] == ["runtime-01"]
    assert listed[0]["status"] == "STARTING"

    beat = client.post(
        "/api/runtimes/runtime-01/heartbeat",
        json={"status": "HEALTHY", "metrics": {"fps": 10.0}, "cameras": []},
    )
    assert beat.status_code == 200
    assert beat.json()["status"] == "HEALTHY"


def test_heartbeat_for_an_unknown_runtime_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/runtimes/runtime-99/heartbeat", json={"status": "HEALTHY"}
    )
    assert response.status_code == 404
