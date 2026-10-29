from contracts.enums import (
    AlarmCategory,
    AlarmSeverity,
    AlarmStatus,
    CameraRole,
    MessageType,
    ProcessingResult,
    ReasonCode,
    ReviewDecision,
)
from contracts.version import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS


def test_schema_version_is_1_0() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS


def test_processing_results_are_closed() -> None:
    assert {r.value for r in ProcessingResult} == {
        "ACCEPTED",
        "DUPLICATE",
        "QUARANTINED",
        "REJECTED",
    }


def test_reason_codes_cover_baseline_and_auto_skip() -> None:
    assert {r.value for r in ReasonCode} == {
        "EXECUTION_AMBIGUOUS",
        "LOW_CONFIDENCE",
        "EVIDENCE_MISSING",
        "CAMERA_CONFLICT",
        "LATE_EVENT",
        "MODEL_VERSION_MISMATCH",
        "RULE_VERSION_MISMATCH",
        "MANUAL_SKIP",
        "AUTO_SKIP",
        "TIMEOUT",
        "UNEXPECTED_STEP",
        "OUT_OF_ORDER",
    }


def test_camera_roles_and_message_types() -> None:
    assert CameraRole.OVERVIEW == "overview"
    assert MessageType.ALARM_CREATED == "alarm.created"


def test_review_decisions_are_closed() -> None:
    assert {d.value for d in ReviewDecision} == {"MARK_COMPLETED", "MARK_FAILED"}


def test_alarm_vocabulary() -> None:
    assert AlarmCategory.DATA_INTEGRITY == "DATA_INTEGRITY"
    assert AlarmSeverity.HIGH == "HIGH"
    assert AlarmStatus.ACKNOWLEDGED == "ACKNOWLEDGED"
