from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True)
class Frame:
    camera_id: str
    frame_seq: int
    captured_at: datetime
    width: int
    height: int
    pixel_format: str
    data: np.ndarray

    def __post_init__(self) -> None:
        if self.data.shape != (self.height, self.width, 3):
            raise ValueError(
                f"frame data {self.data.shape} does not match "
                f"{self.width}x{self.height} BGR"
            )
