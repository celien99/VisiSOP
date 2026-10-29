from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import video_runtime.sources.gige as gige
from video_runtime.config import GigESourceConfig
from video_runtime.sources.gige import GigEHKSource, bayer_to_bgr


def test_bayer_rg8_converts_to_bgr() -> None:
    raw = np.zeros((48, 64), dtype=np.uint8)
    raw[::2, ::2] = 255
    bgr = bayer_to_bgr(raw, "BayerRG8")
    assert bgr.shape == (48, 64, 3)


def test_mono8_becomes_bgr_and_bgr8_passes_through() -> None:
    mono = np.zeros((4, 6), dtype=np.uint8)
    assert bayer_to_bgr(mono, "Mono8").shape == (4, 6, 3)
    bgr = np.zeros((4, 6, 3), dtype=np.uint8)
    assert bayer_to_bgr(bgr, "BGR8") is bgr


def test_unsupported_pixel_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="pixel format"):
        bayer_to_bgr(np.zeros((4, 6), dtype=np.uint8), "RGB8")


def test_missing_harvesters_reports_a_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(gige, "HARVESTERS_AVAILABLE", False)
    source = GigEHKSource(
        GigESourceConfig(cti_path=Path("missing.cti")), camera_id="cam-01"
    )
    with pytest.raises(RuntimeError, match="harvesters"):
        source.start()


class FakeComponent:
    def __init__(self, data, height, width, components):
        self.data = data
        self.height = height
        self.width = width
        self.num_components_per_pixel = components


class FakeBuffer:
    def __init__(self, component):
        self.payload = SimpleNamespace(components=[component])
        self.queued = False

    def queue(self) -> None:
        self.queued = True


class FakeAcquirer:
    def __init__(self, buffer=None):
        self.buffer = buffer
        self.timeouts: list[float] = []

    def fetch(self, timeout=None):
        self.timeouts.append(timeout)
        return self.buffer


def test_fetch_timeout_is_passed_in_seconds(monkeypatch) -> None:
    monkeypatch.setattr(gige, "HARVESTERS_AVAILABLE", True)
    acquirer = FakeAcquirer()
    source = GigEHKSource(
        GigESourceConfig(cti_path=Path("x.cti"), timeout_ms=2000),
        camera_id="cam-01",
        acquirer=acquirer,
    )
    assert source.read() is None
    assert acquirer.timeouts == [2.0]
    assert source.health().status == "UNAVAILABLE"


def test_bgr8_reads_three_channel_component_data() -> None:
    component = FakeComponent(
        np.zeros((4, 18), dtype=np.uint8), height=4, width=6, components=3
    )
    buffer = FakeBuffer(component)
    source = GigEHKSource(
        GigESourceConfig(cti_path=Path("x.cti"), pixel_format="BGR8"),
        camera_id="cam-01",
        acquirer=FakeAcquirer(buffer),
    )
    frame = source.read()
    assert frame is not None
    assert frame.data.shape == (4, 6, 3)
    assert buffer.queued is True


def test_bayer_reads_single_channel_component_data() -> None:
    component = FakeComponent(
        np.zeros((4, 6), dtype=np.uint8), height=4, width=6, components=1
    )
    source = GigEHKSource(
        GigESourceConfig(cti_path=Path("x.cti"), pixel_format="BayerRG8"),
        camera_id="cam-01",
        acquirer=FakeAcquirer(FakeBuffer(component)),
    )
    frame = source.read()
    assert frame is not None
    assert frame.data.shape == (4, 6, 3)


def test_ip_without_serial_reports_the_unsupported_selection(monkeypatch) -> None:
    class FakeHarvester:
        def add_file(self, path) -> None:
            pass

        def update(self) -> None:
            pass

        def reset(self) -> None:
            pass

    monkeypatch.setattr(gige, "HARVESTERS_AVAILABLE", True)
    monkeypatch.setattr(gige, "Harvester", FakeHarvester)
    source = GigEHKSource(
        GigESourceConfig(cti_path=Path("x.cti"), ip="192.168.1.10"),
        camera_id="cam-01",
    )
    with pytest.raises(RuntimeError, match="serial"):
        source.start()


def test_configure_orders_offsets_and_auto_off_before_manual_values() -> None:
    written: list[tuple[str, object]] = []

    class Node:
        def __init__(self, name: str) -> None:
            self.name = name

        @property
        def value(self) -> object:
            return None

        @value.setter
        def value(self, new_value: object) -> None:
            written.append((self.name, new_value))

    class NodeMap:
        Width = Node("Width")
        Height = Node("Height")
        OffsetX = Node("OffsetX")
        OffsetY = Node("OffsetY")
        PixelFormat = Node("PixelFormat")
        ExposureTime = Node("ExposureTime")
        Gain = Node("Gain")
        GevSCPSPacketSize = Node("GevSCPSPacketSize")
        ExposureAuto = Node("ExposureAuto")
        GainAuto = Node("GainAuto")

    source = GigEHKSource(
        GigESourceConfig(cti_path=Path("x.cti"), offset_x=10, offset_y=20),
        camera_id="cam-01",
    )
    source._configure(NodeMap())

    names = [name for name, _ in written]
    assert names.index("OffsetX") < names.index("Width")
    assert names.index("ExposureAuto") < names.index("ExposureTime")
    assert dict(written)["ExposureAuto"] == "Off"
    assert dict(written)["GainAuto"] == "Off"
