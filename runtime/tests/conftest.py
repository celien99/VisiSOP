from datetime import UTC, datetime

import numpy as np
from contracts.events import ModelRef, VisionEvent
from contracts.version import SCHEMA_VERSION

from video_runtime.frame import Frame
from video_runtime.inference.base import Detection

T = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_frame(
    seq: int = 1,
    at: datetime = T,
    camera_id: str = "cam-01",
) -> Frame:
    return Frame(
        camera_id=camera_id,
        frame_seq=seq,
        captured_at=at,
        width=64,
        height=48,
        pixel_format="BGR8",
        data=np.zeros((48, 64, 3), dtype=np.uint8),
    )


def make_detection(
    class_name: str = "bottle",
    confidence: float = 0.9,
    bbox: tuple[float, float, float, float] = (0.1, 0.1, 0.3, 0.3),
) -> Detection:
    class_id = 39 if class_name == "bottle" else 0
    return Detection(
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        bbox=bbox,
    )


def make_event(event_id: str = "evt-1") -> VisionEvent:
    return VisionEvent(
        schema_version=SCHEMA_VERSION,
        event_id=event_id,
        event_type="bottle_in_pickup_zone",
        station_id="st-01",
        camera_id="cam-01",
        occurred_at=T,
        emitted_at=T,
        frame_seq=0,
        confidence=0.9,
        model=ModelRef(name="yolo11n-coco", version="1"),
        attributes={
            "object_class": "bottle",
            "zone": "pickup",
            "bbox": (0.1, 0.1, 0.3, 0.3),
        },
        correlation_key="st-01:pickup:bottle",
    )
