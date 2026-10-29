from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID, uuid4

import contracts.demo  # noqa: F401  (registers the B1 zone event types)
from contracts.catalog import correlation_key_for, validate_attributes
from contracts.events import ModelRef, VisionEvent
from contracts.version import SCHEMA_VERSION

from video_runtime.evidence import EvidenceWriter
from video_runtime.frame import Frame
from video_runtime.zones import ZoneHit

EventIdFactory = Callable[[], UUID]


class EventBuilder:
    """Turns zone hits into contract-valid events, rate-limited per zone."""

    def __init__(
        self,
        station_id: str,
        camera_id: str,
        camera_role: str | None,
        model_name: str,
        model_version: str,
        writer: EvidenceWriter,
    ) -> None:
        self._station_id = station_id
        self._camera_id = camera_id
        self._camera_role = camera_role
        self._model_name = model_name
        self._model_version = model_version
        self._writer = writer
        self._last_emitted: dict[str, datetime] = {}

    def build(
        self,
        frame: Frame,
        hits: Sequence[ZoneHit],
        now: datetime,
        event_id_factory: EventIdFactory = uuid4,
    ) -> list[VisionEvent]:
        events: list[VisionEvent] = []
        for hit in hits:
            last = self._last_emitted.get(hit.zone.name)
            if (
                last is not None
                and (frame.captured_at - last).total_seconds() * 1000
                < hit.zone.emit_interval_ms
            ):
                continue

            attributes = {
                "object_class": hit.detection.class_name,
                "zone": hit.zone.name,
                "bbox": hit.detection.bbox,
            }
            validate_attributes(hit.zone.event_type, attributes)
            event_id = str(event_id_factory())
            evidence_ref = self._writer.write(event_id, frame, hit)
            events.append(
                VisionEvent(
                    schema_version=SCHEMA_VERSION,
                    event_id=event_id,
                    event_type=hit.zone.event_type,
                    station_id=self._station_id,
                    camera_id=self._camera_id,
                    camera_role=self._camera_role,
                    occurred_at=frame.captured_at,
                    emitted_at=now,
                    frame_seq=frame.frame_seq,
                    confidence=hit.detection.confidence,
                    model=ModelRef(name=self._model_name, version=self._model_version),
                    evidence_refs=(evidence_ref,),
                    attributes=attributes,
                    correlation_key=correlation_key_for(
                        hit.zone.event_type,
                        attributes,
                        station_id=self._station_id,
                    ),
                )
            )
            self._last_emitted[hit.zone.name] = frame.captured_at
        return events
