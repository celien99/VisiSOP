import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from contracts.enums import ProcessingResult, ReasonCode
from sop_dsl.schema import (
    CompletionSpec,
    EvidenceSpec,
    FailureRule,
    JoinPolicy,
    SkipIf,
    StepType,
)


class StepStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    TIMED_OUT = "TIMED_OUT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ExecutionStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class MatchedEvent:
    event_id: str
    event_type: str
    confidence: float
    occurred_at: datetime
    camera_id: str
    camera_role: str | None = None
    correlation_key: str | None = None
    accepted: bool = True


@dataclass(frozen=True)
class StepState:
    key: str
    status: StepStatus = StepStatus.PENDING
    activated_at: datetime | None = None
    deadline_at: datetime | None = None
    matched_events: tuple[MatchedEvent, ...] = ()
    reason_code: ReasonCode | None = None
    skipped_reason: str | None = None


def _empty_steps() -> Mapping[str, StepState]:
    return MappingProxyType({})


@dataclass(frozen=True)
class ExecutionState:
    execution_id: str
    status: ExecutionStatus = ExecutionStatus.CREATED
    steps: Mapping[str, StepState] = field(default_factory=_empty_steps)
    started_at: datetime | None = None
    paused_at: datetime | None = None

    def __deepcopy__(self, memo: dict[int, Any]) -> ExecutionState:
        return ExecutionState(
            execution_id=self.execution_id,
            status=self.status,
            steps=MappingProxyType(copy.deepcopy(dict(self.steps), memo)),
            started_at=self.started_at,
            paused_at=self.paused_at,
        )


@dataclass(frozen=True)
class CompiledStep:
    key: str
    name: str
    type: StepType
    completion: CompletionSpec
    required: bool = True
    depends_on: tuple[str, ...] = ()
    timeout_ms: int | None = None
    evidence: EvidenceSpec | None = None
    join_policy: JoinPolicy | None = None
    skip_if: SkipIf | None = None
    failure: FailureRule | None = None


@dataclass(frozen=True)
class SOPGraph:
    sop_key: str
    version: int
    dsl_schema_version: str
    content_hash: str
    steps: Mapping[str, CompiledStep]
    order: tuple[str, ...]
    start_steps: tuple[str, ...]


@dataclass(frozen=True)
class StepTransition:
    step_key: str
    from_status: StepStatus
    to_status: StepStatus
    reason_code: ReasonCode | None = None
    matched_event_ids: tuple[str, ...] = ()
    detail: str | None = None


@dataclass(frozen=True)
class ExecutionTransition:
    from_status: ExecutionStatus
    to_status: ExecutionStatus
    reason_code: ReasonCode | None = None


@dataclass(frozen=True)
class EvidenceUpdate:
    step_key: str
    event: MatchedEvent


@dataclass(frozen=True)
class AlarmIntent:
    category: str
    severity: str
    reason_code: ReasonCode | None = None
    step_key: str | None = None
    source_event_id: str | None = None
    message: str = ""


@dataclass(frozen=True)
class TransitionResult:
    step_transitions: tuple[StepTransition, ...] = ()
    evidence_updates: tuple[EvidenceUpdate, ...] = ()
    execution_transition: ExecutionTransition | None = None
    alarms: tuple[AlarmIntent, ...] = ()
    processing_result: ProcessingResult = ProcessingResult.ACCEPTED
    reason_code: ReasonCode | None = None
    detail: str | None = None
    rule_version: str | None = None
    dsl_version: str | None = None
