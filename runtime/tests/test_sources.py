import cv2
import numpy as np
from conftest import make_frame

from video_runtime.sources.fake import FakeSource
from video_runtime.sources.file import FileSource


def test_file_source_reads_paced_bgr_frames(tmp_path) -> None:
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    for value in (0, 80, 160):
        writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
    writer.release()
    source = FileSource(path, camera_id="cam-01", fps=100.0, loop=False)
    source.start()
    frames = [source.read() for _ in range(3)]
    source.stop()
    assert [f.frame_seq for f in frames if f is not None] == [0, 1, 2]
    assert frames[0] is not None
    assert frames[0].data.shape == (48, 64, 3)
    assert frames[0].pixel_format == "BGR8"
    assert frames[0].camera_id == "cam-01"
    assert source.read() is None


def test_file_source_missing_file_reports_unavailable(tmp_path) -> None:
    source = FileSource(tmp_path / "missing.avi", camera_id="cam-01", fps=10.0)
    source.start()
    assert source.read() is None
    health = source.health()
    assert health.status == "UNAVAILABLE"
    assert health.error
    source.stop()


def test_fake_source_yields_queued_frames_then_none() -> None:
    frames = [make_frame(1), make_frame(2)]
    source = FakeSource(frames)
    source.start()
    assert source.read() is frames[0]
    assert source.read() is frames[1]
    assert source.read() is None
    assert source.health().status == "HEALTHY"
    source.stop()
