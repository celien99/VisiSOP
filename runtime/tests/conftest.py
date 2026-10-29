from datetime import UTC, datetime

import numpy as np

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
