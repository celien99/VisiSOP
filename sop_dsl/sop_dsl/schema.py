from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from contracts.enums import ReasonCode
from contracts.version import SUPPORTED_SCHEMA_VERSIONS
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StepType(StrEnum):
    ACTION = "ACTION"
    CHECKPOINT = "CHECKPOINT"


class CompletionMode(StrEnum):
    EVENT_RULE = "EVENT_RULE"
    STATE_RULE = "STATE_RULE"


class EventCondition(_StrictModel):
    event_type: str
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    stable_for_ms: int = Field(default=0, ge=0)
    within_ms: int | None = Field(default=None, ge=0)
    source_camera_role: str | None = None


class EventRuleCompletion(_StrictModel):
    mode: Literal["EVENT_RULE"] = "EVENT_RULE"
    all: tuple[EventCondition, ...] = ()
    any: tuple[EventCondition, ...] = ()
    not_: tuple[EventCondition, ...] = Field(default=(), alias="not")


class StateRuleCompletion(_StrictModel):
    mode: Literal["STATE_RULE"] = "STATE_RULE"
    all_steps_completed: tuple[str, ...] = ()
    any_steps_completed: tuple[str, ...] = ()


CompletionSpec = Annotated[
    EventRuleCompletion | StateRuleCompletion, Field(discriminator="mode")
]


class JoinPolicy(_StrictModel):
    type: Literal["ALL_REQUIRED", "ANY_OF_N"]
    n: int | None = Field(default=None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"type": data}
        return data

    @model_validator(mode="after")
    def _check_n(self) -> Self:
        if self.type == "ANY_OF_N" and self.n is None:
            raise ValueError("ANY_OF_N requires n")
        if self.type == "ALL_REQUIRED" and self.n is not None:
            raise ValueError("ALL_REQUIRED does not accept n")
        return self


class SkipIf(_StrictModel):
    all_steps_completed: tuple[str, ...] = ()
    event_type: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if bool(self.all_steps_completed) == (self.event_type is not None):
            raise ValueError(
                "skip_if requires exactly one of all_steps_completed or event_type"
            )
        return self


class EvidenceSpec(_StrictModel):
    required: bool
    kind: Literal["keyframe", "clip", "external"]


class FailureRule(_StrictModel):
    event_type: str
    reason_code: ReasonCode


class SOPStepSpec(_StrictModel):
    key: str
    name: str
    type: StepType
    required: bool = True
    depends_on: tuple[str, ...] = ()
    timeout_ms: int | None = Field(default=None, gt=0)
    completion: CompletionSpec
    evidence: EvidenceSpec | None = None
    join_policy: JoinPolicy | None = None
    skip_if: SkipIf | None = None
    failure: FailureRule | None = None

    @model_validator(mode="after")
    def _check_optional_and_join(self) -> Self:
        if not self.required and self.skip_if is None:
            raise ValueError("optional steps must declare skip_if")
        if self.join_policy is not None and not self.depends_on:
            raise ValueError("join_policy requires at least one dependency")
        return self


class SOPSpec(_StrictModel):
    schema_version: str
    sop_key: str
    version: int = Field(ge=1)
    name: str
    steps: tuple[SOPStepSpec, ...] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported schema_version: {value}")
        return value
