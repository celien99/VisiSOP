import asyncio
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.application.outbox import write_outbox
from app.application.outbox_dispatcher import dispatch_once
from app.infrastructure.ws_manager import WsManager
from app.models import OutboxMessage
from contracts.enums import MessageType


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)


def test_dispatch_sends_and_marks(db_session: Session, now: datetime) -> None:
    write_outbox(
        db_session,
        message_type=MessageType.STEP_UPDATED,
        station_id="st-01",
        payload={"execution_id": "e1"},
        now=now,
    )
    db_session.commit()

    manager = WsManager()
    socket = FakeSocket()
    asyncio.run(manager.connect(socket))

    count = asyncio.run(dispatch_once(db_session, manager, now))
    assert count == 1
    assert socket.accepted
    assert socket.sent[0]["type"] == "step.updated"
    row = db_session.exec(select(OutboxMessage)).one()
    assert row.dispatched_at is not None
    assert row.attempts == 1
    assert asyncio.run(dispatch_once(db_session, manager, now)) == 0
