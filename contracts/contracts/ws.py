from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator

from contracts.enums import MessageType
from contracts.version import SUPPORTED_SCHEMA_VERSIONS


class WebSocketMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    message_id: UUID
    type: MessageType
    occurred_at: AwareDatetime
    station_id: str | None
    payload: dict[str, Any]

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported schema_version: {value}")
        return value
