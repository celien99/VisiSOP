import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import contracts.demo  # noqa: F401  (registers the bottle demo event types)
from contracts.catalog import correlation_key_for, get_event_type, validate_attributes
from contracts.events import ModelRef, VisionEvent
from contracts.primitives import get_primitive
from contracts.version import SCHEMA_VERSION
from pydantic import BaseModel

from video_runtime.config import BindingConfig
from video_runtime.evidence import EvidenceWriter
from video_runtime.frame import Frame
from video_runtime.perception import Perception
from video_runtime.primitives import Primitive, build_primitive

logger = logging.getLogger(__name__)

EventIdFactory = Callable[[], UUID]


@dataclass(frozen=True)
class EventBinding:
    binding_id: str
    event_type: str
    primitive: Primitive
    params: BaseModel
    params_hash: str
    emit_interval_ms: int = 500
    heartbeat_ms: int = 2000
    evidence: bool = True


def binding_from_config(config: BindingConfig) -> EventBinding:
    params = get_primitive(config.primitive).params_model.model_validate(config.params)
    payload = json.dumps(
        params.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    params_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return EventBinding(
        binding_id=f"{config.event_type}:{params_hash[:12]}",
        event_type=config.event_type,
        primitive=build_primitive(config.primitive),
        params=params,
        params_hash=params_hash,
        emit_interval_ms=config.emit_interval_ms,
        heartbeat_ms=config.heartbeat_ms,
        evidence=config.evidence,
    )


def _signature(attributes: dict[str, Any]) -> str:
    """Stable observation identity; the moving box and track id are noise."""
    stable = {
        key: value
        for key, value in attributes.items()
        if key not in {"bbox", "track_id"}
    }
    return json.dumps(stable, sort_keys=True, default=str)


class EventBuilder:
    """Turns primitive observations into contract-valid, rate-limited events."""

    def __init__(
        self,
        station_id: str,
        camera_id: str,
        camera_role: str | None,
        model_name: str,
        model_version: str,
        writer: EvidenceWriter,
        bindings: Sequence[EventBinding],
    ) -> None:
        self._station_id = station_id
        self._camera_id = camera_id
        self._camera_role = camera_role
        self._model_name = model_name
        self._model_version = model_version
        self._writer = writer
        self._bindings = tuple(bindings)
        self._last_emitted: dict[int, datetime] = {}
        self._last_signature: dict[int, str | None] = {}

    def build(
        self,
        frame: Frame,
        perception: Perception,
        now: datetime,
        event_id_factory: EventIdFactory = uuid4,
        model_ref: ModelRef | None = None,
    ) -> list[VisionEvent]:
        events: list[VisionEvent] = []
        for index, binding in enumerate(self._bindings):
            spec = get_event_type(binding.event_type)
            primitive = get_primitive(spec.primitive_id)
            observations = binding.primitive.evaluate(perception, binding.params)
            if not observations:
                self._last_signature[index] = None
                continue
            for observation in observations:
                signature = _signature(observation.attributes)
                changed = self._last_signature.get(index) != signature
                last = self._last_emitted.get(index)
                elapsed_ms = (
                    (frame.captured_at - last).total_seconds() * 1000
                    if last is not None
                    else None
                )
                if (
                    changed
                    and elapsed_ms is not None
                    and elapsed_ms < binding.emit_interval_ms
                ):
                    continue
                if not changed and (
                    elapsed_ms is None or elapsed_ms < binding.heartbeat_ms
                ):
                    continue

                attributes = {
                    name: observation.attributes[name]
                    for name in spec.attributes_model.model_fields
                    if name in observation.attributes
                }
                validate_attributes(binding.event_type, attributes)
                event_id = str(event_id_factory())
                evidence_refs: tuple[str, ...] = ()
                if binding.evidence and changed:
                    try:
                        evidence_refs = (
                            self._writer.write(
                                event_id,
                                frame,
                                boxes=observation.boxes,
                                regions=observation.regions,
                                label=(
                                    f"{binding.event_type} {observation.confidence:.2f}"
                                ),
                            ),
                        )
                    except OSError as exc:
                        # Keep the observation: the backend turns missing
                        # evidence into NEEDS_REVIEW/EVIDENCE_MISSING.
                        logger.warning(
                            "evidence write failed for %s: %s", event_id, exc
                        )
                events.append(
                    VisionEvent(
                        schema_version=SCHEMA_VERSION,
                        event_id=event_id,
                        event_type=binding.event_type,
                        station_id=self._station_id,
                        camera_id=self._camera_id,
                        camera_role=self._camera_role,
                        occurred_at=frame.captured_at,
                        emitted_at=now,
                        frame_seq=frame.frame_seq,
                        confidence=observation.confidence,
                        model=model_ref
                        or ModelRef(name=self._model_name, version=self._model_version),
                        primitive_id=primitive.primitive_id,
                        primitive_version=primitive.version,
                        binding_id=binding.binding_id,
                        params_hash=binding.params_hash,
                        observation_ids=(str(uuid4()),),
                        evidence_refs=evidence_refs,
                        attributes=attributes,
                        correlation_key=correlation_key_for(
                            binding.event_type,
                            attributes,
                            station_id=self._station_id,
                        ),
                    )
                )
                self._last_emitted[index] = frame.captured_at
                self._last_signature[index] = signature
        return events
