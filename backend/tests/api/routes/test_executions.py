from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.schemas.execution import ExecutionDetailRead
from app.models import SOPVersion, Station, StepExecution


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
