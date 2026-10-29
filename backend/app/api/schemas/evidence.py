from datetime import datetime

from pydantic import BaseModel

from app.models import EvidenceStatus


class EvidenceRead(BaseModel):
    id: str
    event_id: str
    status: EvidenceStatus
    url: str
    sha256: str | None
    width: int | None
    height: int | None
    created_at: datetime
