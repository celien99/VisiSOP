from collections.abc import Sequence
from dataclasses import dataclass

from video_runtime.config import ZoneConfig
from video_runtime.frame import Frame
from video_runtime.inference.base import Detection


@dataclass(frozen=True)
class Zone:
    name: str
    rect: tuple[float, float, float, float]
    classes: frozenset[str]
    event_type: str
    min_confidence: float
    emit_interval_ms: int

    @classmethod
    def from_config(cls, config: ZoneConfig) -> "Zone":
        return cls(
            name=config.name,
            rect=config.rect,
            classes=frozenset(config.classes),
            event_type=config.event_type,
            min_confidence=config.min_confidence,
            emit_interval_ms=config.emit_interval_ms,
        )


@dataclass(frozen=True)
class ZoneHit:
    zone: Zone
    detection: Detection


class ZoneMapper:
    """Keeps the most confident detection whose center is inside each zone."""

    def __init__(self, zone_configs: Sequence[ZoneConfig]) -> None:
        self._zones = [Zone.from_config(config) for config in zone_configs]

    def map(self, detections: Sequence[Detection], frame: Frame) -> list[ZoneHit]:
        hits: list[ZoneHit] = []
        for zone in self._zones:
            best: Detection | None = None
            for detection in detections:
                if not _matches(zone, detection):
                    continue
                if best is None or detection.confidence > best.confidence:
                    best = detection
            if best is not None:
                hits.append(ZoneHit(zone=zone, detection=best))
        return hits


def _matches(zone: Zone, detection: Detection) -> bool:
    if detection.class_name not in zone.classes:
        return False
    if detection.confidence < zone.min_confidence:
        return False
    x1, y1, x2, y2 = zone.rect
    center_x = (detection.bbox[0] + detection.bbox[2]) / 2
    center_y = (detection.bbox[1] + detection.bbox[3]) / 2
    return x1 <= center_x <= x2 and y1 <= center_y <= y2
