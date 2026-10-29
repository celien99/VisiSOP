from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session

from app.models import AuditRecord


def write_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    detail: dict[str, Any],
    now: datetime,
) -> None:
    session.add(
        AuditRecord(
            id=str(uuid4()),
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            detail=detail,
            created_at=now,
        )
    )
