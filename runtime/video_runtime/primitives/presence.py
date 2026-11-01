from typing import Any

from contracts.primitives import ObjectAbsentParams, ObjectPresentParams
from pydantic import BaseModel

from video_runtime.perception import Perception
from video_runtime.primitives.base import Observation, matching


class ObjectPresent:
    """The most confident instance of a class inside an optional rectangle."""

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, ObjectPresentParams)
        hits = matching(
            perception,
            object_class=params.object_class,
            rect=params.rect,
            min_conf=params.min_conf,
        )
        if not hits:
            return []
        best = max(hits, key=lambda detection: detection.confidence)
        attributes: dict[str, Any] = {
            "object_class": best.class_name,
            "zone": params.zone,
            "bbox": best.bbox,
        }
        track = perception.track_for(best)
        if track is not None:
            attributes["track_id"] = track.track_id
        return [
            Observation(
                primitive_id="object_present",
                primitive_version="1.0",
                attributes=attributes,
                confidence=best.confidence,
                boxes=(best.bbox,),
                regions=(params.rect,) if params.rect is not None else (),
            )
        ]


class ObjectAbsent:
    """Reports absence only after the configured number of missed frames."""

    def __init__(self) -> None:
        self._misses = 0

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, ObjectAbsentParams)
        hits = matching(
            perception,
            object_class=params.object_class,
            rect=params.rect,
            min_conf=params.min_conf,
        )
        if hits:
            self._misses = 0
            best = max(hits, key=lambda detection: detection.confidence)
            return [
                Observation(
                    primitive_id="object_absent",
                    primitive_version="1.0",
                    attributes={
                        "object_class": best.class_name,
                        "zone": params.zone,
                        "present": True,
                        "bbox": best.bbox,
                    },
                    confidence=best.confidence,
                    boxes=(best.bbox,),
                    regions=(params.rect,) if params.rect is not None else (),
                )
            ]
        self._misses += 1
        if self._misses < params.frames:
            return []
        return [
            Observation(
                primitive_id="object_absent",
                primitive_version="1.0",
                attributes={"zone": params.zone, "present": False},
                confidence=1.0,
                regions=(params.rect,) if params.rect is not None else (),
            )
        ]
