from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.enums import MessageType
from contracts.ws import WebSocketMessage

T = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_valid_message() -> None:
    msg = WebSocketMessage(
        schema_version="1.0",
        message_id=uuid4(),
        type=MessageType.ALARM_CREATED,
        occurred_at=T,
        station_id="s1",
        payload={"alarm_id": "a1"},
    )
    assert msg.type is MessageType.ALARM_CREATED


def test_missing_message_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WebSocketMessage(  # type: ignore[call-arg]  # ty: ignore[missing-argument]
            schema_version="1.0",
            type=MessageType.ALARM_CREATED,
            occurred_at=T,
            station_id=None,
            payload={},
        )


def test_naive_time_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WebSocketMessage(
            schema_version="1.0",
            message_id=uuid4(),
            type=MessageType.ALARM_CREATED,
            occurred_at=datetime(2026, 1, 1),  # noqa: DTZ001
            station_id=None,
            payload={},
        )
