import asyncio
from datetime import UTC, datetime
from uuid import UUID

from contracts.enums import MessageType
from contracts.ws import WebSocketMessage
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.db import engine
from app.infrastructure.ws_manager import WsManager, ws_manager
from app.models import OutboxMessage


async def dispatch_once(
    session: Session, manager: WsManager, now: datetime, limit: int = 100
) -> int:
    statement = (
        select(OutboxMessage)
        .where(col(OutboxMessage.dispatched_at).is_(None))
        .order_by(col(OutboxMessage.created_at))
        .limit(limit)
    )
    messages = list(session.exec(statement).all())
    for message in messages:
        envelope = WebSocketMessage(
            schema_version="1.0",
            message_id=UUID(message.message_id),
            type=MessageType(message.type),
            occurred_at=message.created_at,
            station_id=message.station_id,
            payload=message.payload,
        )
        await manager.broadcast(envelope)
        message.dispatched_at = now
        message.attempts += 1
        session.add(message)
    session.commit()
    return len(messages)


async def run_outbox_dispatcher() -> None:
    while True:
        with Session(engine) as session:
            await dispatch_once(session, ws_manager, datetime.now(UTC))
        await asyncio.sleep(settings.OUTBOX_POLL_MS / 1000)
