import dataclasses

import pytest
from contracts.enums import ProcessingResult, ReasonCode

from app.domain.sop.model import (
    AlarmIntent,
    ExecutionStatus,
    StepState,
    StepStatus,
    TransitionResult,
)


def test_step_status_values() -> None:
    assert StepStatus.ACTIVE == "ACTIVE"
    assert ExecutionStatus.NEEDS_REVIEW == "NEEDS_REVIEW"


def test_models_are_frozen() -> None:
    state = StepState(key="a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.status = StepStatus.COMPLETED  # type: ignore[misc]  # ty: ignore[invalid-assignment]


def test_transition_result_defaults_to_accepted() -> None:
    result = TransitionResult()
    assert result.processing_result is ProcessingResult.ACCEPTED
    assert result.step_transitions == ()


def test_alarm_carries_reason_code() -> None:
    alarm = AlarmIntent(
        category="PROCESS_COMPLIANCE",
        severity="HIGH",
        reason_code=ReasonCode.TIMEOUT,
        step_key="a",
    )
    assert alarm.reason_code is ReasonCode.TIMEOUT
