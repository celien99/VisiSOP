from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from contracts.runtime import (
    CameraHealthStatus,
    CameraStatus,
    RuntimeHeartbeat,
    RuntimeStatus,
)

T = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestRuntimeHeartbeat:
    def test_accepts_aware_frame_time_and_metrics(self) -> None:
        beat = RuntimeHeartbeat(
            status=RuntimeStatus.HEALTHY,
            metrics={"fps": 9.8},
            cameras=(
                CameraStatus(
                    camera_id="cam-01",
                    status=CameraHealthStatus.HEALTHY,
                    last_frame_at=T,
                    fps=9.8,
                    inference_ms=42.0,
                    dropped_frames=0,
                    error=None,
                ),
            ),
        )
        assert beat.cameras[0].camera_id == "cam-01"

    def test_rejects_naive_frame_time(self) -> None:
        with pytest.raises(ValidationError):
            CameraStatus(
                camera_id="cam-01",
                status=CameraHealthStatus.HEALTHY,
                last_frame_at=datetime(2026, 1, 1),  # noqa: DTZ001
                fps=1.0,
                inference_ms=1.0,
                dropped_frames=0,
                error=None,
            )
