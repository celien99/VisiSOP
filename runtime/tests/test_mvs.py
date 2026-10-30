from datetime import UTC

import numpy as np
import pytest

import video_runtime.sources.mvs as mvs
from video_runtime.config import MvsSourceConfig
from video_runtime.sources.mvs import MvsSource, matches_device, to_bgr


class FakeKit:
    def __init__(self, frames: list[np.ndarray | None]) -> None:
        self.frames = list(frames)
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def grab(self, timeout_ms: int) -> np.ndarray | None:
        return self.frames.pop(0) if self.frames else None

    def close(self) -> None:
        self.closed = True


def test_device_selection_prefers_the_serial() -> None:
    config = MvsSourceConfig(serial="DA9184675")
    assert matches_device(config, serial_number="DA9184675", current_ip="10.0.0.2")
    assert not matches_device(config, serial_number="other", current_ip="10.0.0.2")
    by_ip = MvsSourceConfig(ip="10.172.30.1")
    assert matches_device(by_ip, serial_number="x", current_ip="10.172.30.1")
    assert matches_device(MvsSourceConfig(), serial_number="x", current_ip="y")


def test_rgb8_packed_already_arrives_as_bgr() -> None:
    packed = np.zeros((2, 2, 3), dtype=np.uint8)
    packed[..., 0], packed[..., 1], packed[..., 2] = 10, 20, 30
    out = to_bgr(packed.reshape(-1), 2, 2, 0x02180014)
    assert out[0, 0].tolist() == [10, 20, 30]


def test_bgr8_packed_arrives_as_rgb() -> None:
    packed = np.zeros((2, 2, 3), dtype=np.uint8)
    packed[..., 0], packed[..., 1], packed[..., 2] = 10, 20, 30
    out = to_bgr(packed.reshape(-1), 2, 2, 0x02180015)
    assert out[0, 0].tolist() == [30, 20, 10]


def test_mono8_and_bayer_become_three_channel_bgr() -> None:
    mono = np.zeros((4, 6), dtype=np.uint8)
    assert to_bgr(mono.reshape(-1), 6, 4, 0x01080001).shape == (4, 6, 3)
    assert to_bgr(mono.reshape(-1), 6, 4, 0x01080009).shape == (4, 6, 3)


def test_yuyv_becomes_three_channel_bgr() -> None:
    yuyv = np.zeros((4, 6, 2), dtype=np.uint8)
    assert to_bgr(yuyv.reshape(-1), 6, 4, 0x02100032).shape == (4, 6, 3)


def test_unknown_pixel_type_names_the_problem() -> None:
    with pytest.raises(RuntimeError, match="unsupported camera pixel type"):
        to_bgr(np.zeros(16, dtype=np.uint8), 4, 2, 0x0108000A)


def test_read_returns_a_bgr_frame_and_advances_the_sequence() -> None:
    kit = FakeKit([np.zeros((48, 64, 3), dtype=np.uint8)])
    source = MvsSource(MvsSourceConfig(serial="s"), camera_id="cam-01", kit=kit)
    source.start()
    frame = source.read()
    assert kit.opened is True
    assert frame is not None
    assert frame.frame_seq == 0
    assert frame.width == 64 and frame.height == 48
    assert frame.pixel_format == "BGR8"
    assert frame.captured_at.tzinfo is UTC
    assert source.health().status == "HEALTHY"


def test_a_timed_out_grab_reports_unavailable() -> None:
    kit = FakeKit([None])
    source = MvsSource(MvsSourceConfig(serial="s"), camera_id="cam-01", kit=kit)
    source.start()
    assert source.read() is None
    assert source.health().status == "UNAVAILABLE"
    assert "timed out" in (source.health().error or "")


def test_start_failure_is_reported_and_the_kit_is_closed(monkeypatch) -> None:
    kit = FakeKit([])

    def fail() -> None:
        raise RuntimeError("no camera")

    monkeypatch.setattr(kit, "open", fail)
    source = MvsSource(MvsSourceConfig(serial="s"), camera_id="cam-01", kit=kit)
    with pytest.raises(RuntimeError, match="MVS camera"):
        source.start()
    assert kit.closed is True
    assert source.health().status == "UNAVAILABLE"


def test_missing_sdk_reports_a_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(
        mvs, "load_sdk", lambda: _raise(RuntimeError("MVS SDK Python bindings"))
    )
    source = MvsSource(MvsSourceConfig(serial="s"), camera_id="cam-01")
    with pytest.raises(RuntimeError, match="MVS SDK"):
        source.start()


def _raise(exc: Exception) -> None:
    raise exc
