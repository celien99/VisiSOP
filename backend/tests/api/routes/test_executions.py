import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.schemas.execution import ExecutionDetailRead
from app.models import SOPVersion, Station, StepExecution
from tests.conftest import DEMO_SOP_PATH


def test_create_activates_start_step_and_second_start_conflicts(
    client: TestClient, published_sop: SOPVersion, seeded_station: Station
) -> None:
    first = client.post(
        "/api/stations/st-01/executions",
        json={"sop_version_id": published_sop.id},
    )
    assert first.status_code == 201
    body = first.json()
    assert body["status"] == "RUNNING"
    assert {step["key"]: step["status"] for step in body["steps"]} == {
        "pick_bottle": "ACTIVE",
        "place_bottle": "PENDING",
        "verify_placement": "PENDING",
    }

    second = client.post(
        "/api/stations/st-01/executions",
        json={"sop_version_id": published_sop.id},
    )
    assert second.status_code == 409


def test_pause_resume_extends_active_deadline(
    client: TestClient, active_execution: ExecutionDetailRead, db_session: Session
) -> None:
    before = client.get(f"/api/executions/{active_execution.id}").json()
    deadline = datetime.fromisoformat(before["steps"][0]["deadline_at"])

    paused_response = client.post(f"/api/executions/{active_execution.id}/pause")
    assert paused_response.status_code == 200
    db_session.expire_all()
    paused = client.get(f"/api/executions/{active_execution.id}").json()
    assert paused["status"] == "PAUSED"

    resumed_response = client.post(f"/api/executions/{active_execution.id}/resume")
    assert resumed_response.status_code == 200
    resumed = client.get(f"/api/executions/{active_execution.id}").json()
    assert resumed["status"] == "RUNNING"
    assert datetime.fromisoformat(resumed["steps"][0]["deadline_at"]) > deadline


def test_review_is_rejected_for_a_step_that_is_not_needs_review(
    client: TestClient, active_execution: ExecutionDetailRead
) -> None:
    response = client.post(
        f"/api/executions/{active_execution.id}/steps/pick_bottle/review",
        json={"operator": "tester", "decision": "MARK_COMPLETED", "reason": "seen"},
    )
    assert response.status_code == 409


def test_review_requires_an_operator(
    client: TestClient, active_execution: ExecutionDetailRead
) -> None:
    response = client.post(
        f"/api/executions/{active_execution.id}/steps/pick_bottle/review",
        json={"operator": "", "decision": "MARK_COMPLETED", "reason": "seen"},
    )
    assert response.status_code == 422


def test_review_completion_starts_the_dependent_step(
    client: TestClient,
    db_session: Session,
    active_execution: ExecutionDetailRead,
) -> None:
    pick = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert pick is not None
    pick.status = "NEEDS_REVIEW"  # type: ignore[assignment]
    pick.reason_code = "EVIDENCE_MISSING"  # type: ignore[assignment]
    db_session.add(pick)
    db_session.commit()

    response = client.post(
        f"/api/executions/{active_execution.id}/steps/pick_bottle/review",
        json={"operator": "tester", "decision": "MARK_COMPLETED", "reason": "checked"},
    )
    assert response.status_code == 200
    db_session.expire_all()
    place = db_session.get(StepExecution, (active_execution.id, "place_bottle"))
    assert place is not None
    assert place.status == "ACTIVE"


def test_detail_list_and_timeline(
    client: TestClient, active_execution: ExecutionDetailRead
) -> None:
    detail = client.get(f"/api/executions/{active_execution.id}").json()
    assert len(detail["steps"]) == 3
    assert detail["allowed_actions"] == ["PAUSE", "ABORT"]

    listed = client.get(
        "/api/executions", params={"station_id": "st-01"}
    ).json()
    assert [item["id"] for item in listed] == [active_execution.id]

    timeline = client.get(
        f"/api/executions/{active_execution.id}/timeline"
    ).json()
    assert any(item["type"] == "STEP" for item in timeline)


def test_abort_finishes_the_execution_and_cannot_repeat(
    client: TestClient, active_execution: ExecutionDetailRead
) -> None:
    aborted = client.post(
        f"/api/executions/{active_execution.id}/abort", json={"reason": "demo"}
    )
    assert aborted.status_code == 200
    assert aborted.json()["status"] == "ABORTED"
    assert aborted.json()["finished_at"] is not None
    assert (
        client.post(
            f"/api/executions/{active_execution.id}/abort",
            json={"reason": "again"},
        ).status_code
        == 409
    )


def test_skip_required_step_is_rejected(
    client: TestClient, active_execution: ExecutionDetailRead
) -> None:
    response = client.post(
        f"/api/executions/{active_execution.id}/steps/pick_bottle/skip",
        json={"operator": "tester", "reason": "not allowed"},
    )
    assert response.status_code == 409


def test_review_with_unknown_evidence_is_rejected(
    client: TestClient,
    db_session: Session,
    active_execution: ExecutionDetailRead,
) -> None:
    pick = db_session.get(StepExecution, (active_execution.id, "pick_bottle"))
    assert pick is not None
    pick.status = "NEEDS_REVIEW"  # type: ignore[assignment]
    db_session.add(pick)
    db_session.commit()

    response = client.post(
        f"/api/executions/{active_execution.id}/steps/pick_bottle/review",
        json={
            "operator": "tester",
            "decision": "MARK_COMPLETED",
            "reason": "checked",
            "evidence_ids": ["missing-evidence"],
        },
    )
    assert response.status_code == 422


def test_create_requires_a_published_version(
    client: TestClient, seeded_station: Station
) -> None:
    dsl = json.loads(DEMO_SOP_PATH.read_text(encoding="utf-8"))
    created = client.post(
        "/api/sops", json={"key": "draft_only", "name": "Draft", "dsl": dsl}
    )
    version_id = created.json()["id"]
    response = client.post(
        "/api/stations/st-01/executions",
        json={"sop_version_id": version_id},
    )
    assert response.status_code == 422
    assert (
        client.post(
            "/api/stations/nope/executions",
            json={"sop_version_id": version_id},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/stations/st-01/executions",
            json={"sop_version_id": "nope"},
        ).status_code
        == 404
    )
