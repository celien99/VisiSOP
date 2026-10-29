from fastapi.testclient import TestClient

from app.models import Alarm


def test_acknowledge_and_resolve(client: TestClient, open_alarm: Alarm) -> None:
    ack = client.post(
        f"/api/alarms/{open_alarm.id}/acknowledge",
        json={"operator": "tester", "comment": "seen"},
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "ACKNOWLEDGED"

    resolved = client.post(
        f"/api/alarms/{open_alarm.id}/resolve", json={"operator": "tester"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"

    assert (
        client.post(
            f"/api/alarms/{open_alarm.id}/acknowledge",
            json={"operator": "tester"},
        ).status_code
        == 409
    )


def test_list_alarms_filters_by_status(client: TestClient, open_alarm: Alarm) -> None:
    assert len(client.get("/api/alarms", params={"status": "OPEN"}).json()) == 1
    assert client.get("/api/alarms", params={"status": "RESOLVED"}).json() == []


def test_action_requires_an_operator(client: TestClient, open_alarm: Alarm) -> None:
    response = client.post(
        f"/api/alarms/{open_alarm.id}/resolve", json={"operator": ""}
    )
    assert response.status_code == 422
