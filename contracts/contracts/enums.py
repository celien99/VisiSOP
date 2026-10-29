from enum import StrEnum


class ProcessingResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class ReasonCode(StrEnum):
    EXECUTION_AMBIGUOUS = "EXECUTION_AMBIGUOUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    CAMERA_CONFLICT = "CAMERA_CONFLICT"
    LATE_EVENT = "LATE_EVENT"
    MODEL_VERSION_MISMATCH = "MODEL_VERSION_MISMATCH"
    RULE_VERSION_MISMATCH = "RULE_VERSION_MISMATCH"
    MANUAL_SKIP = "MANUAL_SKIP"
    AUTO_SKIP = "AUTO_SKIP"
    TIMEOUT = "TIMEOUT"
    UNEXPECTED_STEP = "UNEXPECTED_STEP"
    OUT_OF_ORDER = "OUT_OF_ORDER"


class CameraRole(StrEnum):
    OVERVIEW = "overview"
    HANDS = "hands"
    TOOL = "tool"
    PART_STATE = "part_state"


class MessageType(StrEnum):
    ALARM_CREATED = "alarm.created"
    ALARM_UPDATED = "alarm.updated"
    EXECUTION_UPDATED = "execution.updated"
    STEP_UPDATED = "step.updated"
    RUNTIME_HEALTH = "runtime.health"


class ReviewDecision(StrEnum):
    MARK_COMPLETED = "MARK_COMPLETED"
    MARK_FAILED = "MARK_FAILED"


class AlarmCategory(StrEnum):
    PROCESS_COMPLIANCE = "PROCESS_COMPLIANCE"
    VISION_QUALITY = "VISION_QUALITY"
    DEVICE_HEALTH = "DEVICE_HEALTH"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    SYSTEM = "SYSTEM"


class AlarmSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlarmStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
