from conftest import make_frame

from video_runtime.buffer import FrameBuffer


def test_buffer_keeps_latest_and_counts_drops() -> None:
    buffer = FrameBuffer(maxsize=1)
    buffer.put(make_frame(1))
    buffer.put(make_frame(2))
    latest = buffer.snapshot()
    assert latest is not None
    assert latest.frame_seq == 2
    assert buffer.dropped == 1


def test_get_returns_a_queued_frame_then_times_out() -> None:
    buffer = FrameBuffer(maxsize=1)
    buffer.put(make_frame(1))
    assert buffer.get(timeout=0.1) is not None
    assert buffer.get(timeout=0.01) is None
