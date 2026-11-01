from contracts.primitives import StateClassifyParams
from pydantic import BaseModel

from video_runtime.perception import Perception
from video_runtime.primitives.base import Observation, centre_inside


class StateClassify:
    """Maps the most confident state-labelled detection in a ROI to a state."""

    def evaluate(self, perception: Perception, params: BaseModel) -> list[Observation]:
        assert isinstance(params, StateClassifyParams)
        states = set(params.states)
        hits = [
            detection
            for detection in perception.detections
            if detection.class_name in states
            and detection.confidence >= params.min_conf
            and centre_inside(detection.bbox, params.roi)
        ]
        if not hits:
            return []
        best = max(hits, key=lambda detection: detection.confidence)
        return [
            Observation(
                primitive_id="state_classify",
                primitive_version="1.0",
                attributes={"state": best.class_name},
                confidence=best.confidence,
                boxes=(best.bbox,),
                regions=(params.roi,),
            )
        ]
