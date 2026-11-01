from typing import Any

from contracts.primitives import ObjectInZoneParams
from pydantic import BaseModel

from video_runtime.perception import Perception
from video_runtime.primitives.base import Observation, matching


class ObjectInZone:
    """The most confident instance whose centre lies inside a rectangle."""

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, ObjectInZoneParams)
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
                primitive_id="object_in_zone",
                primitive_version="1.0",
                attributes=attributes,
                confidence=best.confidence,
                boxes=(best.bbox,),
                regions=(params.rect,),
            )
        ]
