from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.api.schemas.execution import ExecutionDetailRead


def test_ingest_and_duplicate_over_http(
    client: TestClient,
    active_execution: ExecutionDetailRead,
    event_payload: dict[str, object],
) -> None:
    first = client.post("/api/events", json=event_payload)
    assert first.status_code == 202
    assert first.json()["result"] == "ACCEPTED"

    second = client.post("/api/events", json=event_payload)
    assert second.status_code == 202
    assert second.json()["result"] == "DUPLICATE"


def test_quarantined_event_can_be_assigned(
    client: TestClient,
    active_execution: ExecutionDetailRead,
    make_zone_event,
    now: datetime,
) -> None:
    event = make_zone_event("evt-q", "pickup", now)
    payload = event.model_dump(mode="json")
    payload["execution_id"] = "missing-exec"

    first = client.post("/api/events", json=payload)
    assert first.status_code == 202
    assert first.json()["result"] == "QUARANTINED"

    listed = client.get("/api/events", params={"result": "QUARANTINED"}).json()
    assert [item["event_id"] for item in listed] == ["evt-q"]

    assigned = client.post(
        "/api/events/evt-q/assign",
        json={"execution_id": active_execution.id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["result"] == "ACCEPTED"


def test_assign_rejects_a_non_quarantined_event(
    client: TestClient,
    active_execution: ExecutionDetailRead,
    event_payload: dict[str, object],
) -> None:
    accepted = client.post("/api/events", json=event_payload)
    assert accepted.json()["result"] == "ACCEPTED"
    response = client.post(
        "/api/events/evt-1/assign",
        json={"execution_id": active_execution.id},
    )
    assert response.status_code == 409


def test_happy_path_completes_the_execution_over_http(
    client: TestClient,
    active_execution: ExecutionDetailRead,
    make_zone_event,
    now: datetime,
) -> None:
    def post(event_id: str, zone: str, at: datetime) -> None:
        event = make_zone_event(event_id, zone, at)
        response = client.post(
            "/api/events", json=event.model_dump(mode="json")
        )
        assert response.status_code == 202
        assert response.json()["result"] == "ACCEPTED"

    post("p1", "pickup", now)
    post("p2", "pickup", now + timedelta(milliseconds=600))
    post("t1", "target", now + timedelta(milliseconds=1200))
    post("t2", "target", now + timedelta(milliseconds=1800))

    detail = client.get(f"/api/executions/{active_execution.id}").json()
    assert detail["status"] == "COMPLETED"
    by_key = {step["key"]: step for step in detail["steps"]}
    assert {key: step["status"] for key, step in by_key.items()} == {
        "pick_bottle": "COMPLETED",
        "place_bottle": "COMPLETED",
        "verify_placement": "COMPLETED",
    }
    assert any(
        asset["status"] == "AVAILABLE"
        for asset in by_key["pick_bottle"]["evidence"]
    )
    assert any(
        asset["status"] == "AVAILABLE"
        for asset in by_key["place_bottle"]["evidence"]
    )
