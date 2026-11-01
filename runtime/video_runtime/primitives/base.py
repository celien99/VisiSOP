from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from video_runtime.inference.base import Detection
from video_runtime.perception import BBox, Perception


@dataclass(frozen=True)
class Observation:
    primitive_id: str
    primitive_version: str
    attributes: dict[str, Any]
    confidence: float
    boxes: tuple[BBox, ...] = ()
    regions: tuple[BBox, ...] = ()


class Primitive(Protocol):
    def evaluate(
        self, perception: Perception, params: BaseModel
    ) -> list[Observation]: ...


def centre(bbox: BBox) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def centre_inside(bbox: BBox, rect: BBox) -> bool:
    cx, cy = centre(bbox)
    return rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]


def matching(
    perception: Perception,
    *,
    object_class: str,
    rect: BBox | None,
    min_conf: float,
) -> Sequence[Detection]:
    return [
        detection
        for detection in perception.detections
        if detection.class_name == object_class
        and detection.confidence >= min_conf
        and (rect is None or centre_inside(detection.bbox, rect))
    ]
