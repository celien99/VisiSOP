from datetime import datetime
from typing import Any
from uuid import uuid4

from contracts.enums import MessageType
from sqlmodel import Session

from app.models import OutboxMessage


def write_outbox(
    session: Session,
    *,
    message_type: MessageType,
    station_id: str | None,
    payload: dict[str, Any],
    now: datetime,
) -> OutboxMessage:
    message = OutboxMessage(
        id=str(uuid4()),
        message_id=str(uuid4()),
        type=message_type,
        station_id=station_id,
        payload=payload,
        created_at=now,
    )
    session.add(message)
    return message
