from contracts.primitives import CountThresholdParams
from pydantic import BaseModel

from video_runtime.perception import Perception
from video_runtime.primitives.base import Observation, matching


class CountThreshold:
    """Counts object instances inside a rectangle; emits every evaluation."""

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, CountThresholdParams)
        hits = matching(
            perception,
            object_class=params.object_class,
            rect=params.roi,
            min_conf=params.min_conf,
        )
        confidence = min((detection.confidence for detection in hits), default=0.0)
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
