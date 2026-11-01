from contracts.primitives import OrientationMatchParams
from pydantic import BaseModel

from video_runtime.perception import Perception
from video_runtime.primitives.base import Observation, centre_inside


class OrientationMatch:
    """Reads orientation from model classes such as CORRECT / REVERSED."""

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, OrientationMatchParams)
        labels = {
            params.correct_class: "CORRECT",
            params.reversed_class: "REVERSED",
        }
        hits = [
            detection
            for detection in perception.detections
            if detection.class_name in labels
            and detection.confidence >= params.min_conf
            and centre_inside(detection.bbox, params.roi)
        ]
        if not hits:
            return []
        best = max(hits, key=lambda detection: detection.confidence)
        return [
            Observation(
                primitive_id="orientation_match",
                primitive_version="1.0",
                attributes={
                    "compartment": params.compartment,
                    "orientation": labels[best.class_name],
                },
                confidence=best.confidence,
                boxes=(best.bbox,),
                regions=(params.roi,),
            )
        ]
