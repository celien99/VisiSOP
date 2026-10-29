from datetime import UTC, datetime

import numpy as np

from video_runtime.frame import Frame

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
