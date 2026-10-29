import json
from pathlib import Path

from fastapi.testclient import TestClient

SOP_PATH = Path(__file__).parents[3] / "app" / "seed" / "bottle_transfer.json"


def test_create_validate_publish_and_new_draft(client: TestClient) -> None:
    payload = {
        "key": "bottle_transfer",
        "name": "瓶体转移演示",
        "dsl": json.loads(SOP_PATH.read_text(encoding="utf-8")),
    }
    created = client.post("/api/sops", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["version"] == 1
    assert body["status"] == "DRAFT"
    sop_id = body["sop_id"]

    report = client.post(f"/api/sops/{sop_id}/validate")
    assert report.json()["valid"] is True

    published = client.post(f"/api/sops/{sop_id}/publish").json()
    assert published["status"] == "PUBLISHED"
    assert published["published_at"]

    edited = client.patch(f"/api/sops/{sop_id}", json={"dsl": payload["dsl"]})
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["status"] == "DRAFT"

    versions = client.get(f"/api/sops/{sop_id}/versions").json()
    assert [version["version"] for version in versions] == [2, 1]

    detail = client.get(f"/api/sops/{sop_id}").json()
    assert detail["latest_published_version_id"] == versions[1]["id"]
    assert [step["key"] for step in detail["versions"][1]["steps"]] == [
        "pick_bottle",
        "place_bottle",
        "verify_placement",
    ]


def test_unknown_event_type_is_a_validation_issue(client: TestClient) -> None:
    dsl = json.loads(SOP_PATH.read_text(encoding="utf-8"))
    dsl["steps"][0]["completion"]["all"][0]["event_type"] = "not_registered"
    created = client.post("/api/sops", json={"key": "bad", "name": "Bad", "dsl": dsl})
    assert created.status_code == 201
    report = client.post(f"/api/sops/{created.json()['sop_id']}/validate").json()
    assert report["valid"] is False
    assert any(issue["code"] == "UNKNOWN_EVENT_TYPE" for issue in report["issues"])


def test_publish_rejects_a_published_version(client: TestClient) -> None:
    payload = {
        "key": "bottle_transfer",
        "name": "瓶体转移演示",
        "dsl": json.loads(SOP_PATH.read_text(encoding="utf-8")),
    }
    sop_id = client.post("/api/sops", json=payload).json()["sop_id"]
    assert client.post(f"/api/sops/{sop_id}/publish").status_code == 200
    assert client.post(f"/api/sops/{sop_id}/publish").status_code == 409
