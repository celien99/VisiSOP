from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from contracts.enums import ReasonCode
from contracts.version import SUPPORTED_SCHEMA_VERSIONS


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _VersionedModel(_ContractModel):
    schema_version: str

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported schema_version: {value}")
        return value


class ModelRef(_ContractModel):
    name: str
    version: str


class Observation(_VersionedModel):
    observation_id: str
    station_id: str
    camera_id: str
    occurred_at: AwareDatetime
    frame_seq: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    model: ModelRef
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    execution_id: str | None = None


class VisionEvent(_VersionedModel):
    event_id: str
    event_type: str
    station_id: str
    camera_id: str
    camera_role: str | None = None
    occurred_at: AwareDatetime
    emitted_at: AwareDatetime
    frame_seq: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    model: ModelRef
    observation_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    attributes: dict[str, Any] = Field(default_factory=dict)
    correlation_key: str | None = None


class RoutedSOPEvent(VisionEvent):
    execution_id: str
    resolution_method: str
    resolved_at: AwareDatetime
    resolver_rule_version: str
    candidate_ids: tuple[str, ...] = ()
    reason_code: ReasonCode | None = None
