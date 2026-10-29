from collections.abc import Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Any

from contracts.enums import ReasonCode

from app.domain.sop.model import (
    ExecutionState,
    ExecutionStatus,
    MatchedEvent,
    SOPGraph,
    StepState,
    StepStatus,
)
from app.models import SOPExecution, StepExecution


def matched_to_json(event: MatchedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "confidence": event.confidence,
        "occurred_at": event.occurred_at.isoformat(),
        "camera_id": event.camera_id,
        "camera_role": event.camera_role,
        "correlation_key": event.correlation_key,
        "accepted": event.accepted,
    }


def matched_from_json(data: dict[str, Any]) -> MatchedEvent:
    return MatchedEvent(
        event_id=data["event_id"],
        event_type=data["event_type"],
        confidence=float(data["confidence"]),
        occurred_at=datetime.fromisoformat(data["occurred_at"]),
        camera_id=data["camera_id"],
        camera_role=data.get("camera_role"),
        correlation_key=data.get("correlation_key"),
        accepted=bool(data.get("accepted", True)),
    )


def state_from_rows(
    execution: SOPExecution,
    step_rows: Sequence[StepExecution],
    graph: SOPGraph,
) -> ExecutionState:
    steps: dict[str, StepState] = {}
    for row in step_rows:
        steps[row.step_key] = StepState(
            key=row.step_key,
            status=StepStatus(row.status),
            activated_at=row.activated_at,
            deadline_at=row.deadline_at,
            matched_events=tuple(
                matched_from_json(event) for event in row.matched_events
            ),
            reason_code=ReasonCode(row.reason_code) if row.reason_code else None,
            skipped_reason=row.skipped_reason,
        )
    for key in graph.order:
        steps.setdefault(key, StepState(key=key))
    return ExecutionState(
        execution_id=execution.id,
        status=ExecutionStatus(execution.status),
        steps=MappingProxyType(steps),
        started_at=execution.started_at,
        paused_at=execution.paused_at,
    )
