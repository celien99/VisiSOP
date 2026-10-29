from fastapi.testclient import TestClient

from app.models import Station


def test_create_camera_rejects_a_duplicate_code(
    client: TestClient, seeded_station: Station
) -> None:
    payload = {
        "code": "CAM-01",
        "name": "重复相机",
        "runtime_id": "runtime-01",
        "source_type": "gige",
    }
    response = client.post("/api/cameras", json=payload)
    assert response.status_code == 409


def test_update_camera_changes_only_sent_fields(
    client: TestClient, seeded_station: Station
) -> None:
    response = client.patch("/api/cameras/cam-01", json={"name": "新名称"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "新名称"
    assert body["code"] == "CAM-01"
    assert "source_config" not in body


def test_camera_health_is_unknown_without_a_heartbeat(
    client: TestClient, seeded_station: Station
) -> None:
    health = client.get("/api/cameras/cam-01/health").json()
    assert health["status"] == "UNKNOWN"


def test_binding_the_same_camera_to_another_station_conflicts(
    client: TestClient, seeded_station: Station
) -> None:
    created = client.post(
        "/api/stations", json={"code": "ST-02", "name": "工位二"}
    )
    station_id = created.json()["id"]
    response = client.post(
        f"/api/stations/{station_id}/cameras",
        json={"camera_id": "cam-01", "role": "overview"},
    )
    assert response.status_code == 409
