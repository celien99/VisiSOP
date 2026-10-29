from datetime import datetime
from uuid import uuid4

from contracts.events import VisionEvent
from sqlmodel import Session

from app.infrastructure.evidence_store import EvidenceStore, IngestedEvidence
from app.models import EventEvidenceLink, EvidenceAsset, EvidenceStatus


class EvidenceService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def ingest_for_event(
        self, session: Session, event: VisionEvent, now: datetime
    ) -> list[EvidenceAsset]:
        assets: list[EvidenceAsset] = []
        for ref in event.evidence_refs:
            try:
                [ingested] = self.store.ingest(event.event_id, [ref])
            except ValueError:
                # A bad ref never fails the event; it becomes explicit evidence debt.
                ingested = IngestedEvidence(
                    storage_key=ref,
                    final_key=None,
                    sha256=None,
                    byte_size=None,
                    width=None,
                    height=None,
                    status=EvidenceStatus.MISSING,
                )
            asset = EvidenceAsset(
                id=str(uuid4()),
                event_id=event.event_id,
                storage_key=ingested.storage_key,
                sha256=ingested.sha256,
                byte_size=ingested.byte_size,
                width=ingested.width,
                height=ingested.height,
                status=ingested.status,
                created_at=now,
                verified_at=(
                    now if ingested.status is EvidenceStatus.AVAILABLE else None
                ),
            )
            session.add(asset)
            # No ORM relationship between the two tables; flush so the FK holds.
            session.flush()
            session.add(
                EventEvidenceLink(event_id=event.event_id, evidence_id=asset.id)
            )
            assets.append(asset)
        return assets
