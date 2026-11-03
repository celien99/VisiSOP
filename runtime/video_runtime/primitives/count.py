from contracts.primitives import CountThresholdParams
from pydantic import BaseModel

from video_runtime.inference.base import Detection
from video_runtime.perception import BBox, Perception
from video_runtime.primitives.base import Observation, centre_inside

_IOU_LIMIT = 0.5


def _iou(a: BBox, b: BBox) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / max(area_a + area_b - intersection, 1e-9)


def _distinct(hits: list[Detection]) -> list[Detection]:
    """Drop duplicate boxes a model may emit for one instance across classes."""
    kept: list[Detection] = []
    for detection in sorted(hits, key=lambda item: item.confidence, reverse=True):
        if all(_iou(detection.bbox, other.bbox) < _IOU_LIMIT for other in kept):
            kept.append(detection)
    return kept


class CountThreshold:
    """Counts object instances inside a rectangle; emits every evaluation."""

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, CountThresholdParams)
        classes = {params.object_class, *params.count_classes}
        hits = _distinct(
            [
                detection
                for detection in perception.detections
                if detection.class_name in classes
                and detection.confidence >= params.min_conf
                and centre_inside(detection.bbox, params.roi)
            ]
        )
        confidence = (
            sum(detection.confidence for detection in hits) / len(hits) if hits else 0.0
        )
        return [
            Observation(
                primitive_id="count_threshold",
                primitive_version="1.0",
                attributes={
                    "compartment": params.compartment,
                    "count": len(hits),
                    "slots": params.slots,
                },
                confidence=confidence,
                boxes=tuple(detection.bbox for detection in hits),
                regions=(params.roi,),
            )
        ]
