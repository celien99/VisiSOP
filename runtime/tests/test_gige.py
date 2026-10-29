from pathlib import Path

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
