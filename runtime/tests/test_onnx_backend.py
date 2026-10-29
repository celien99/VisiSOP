from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import make_frame

from video_runtime.inference.onnx_yolo import OnnxYoloBackend

COCO_NAMES = (
    (Path(__file__).parents[1] / "models" / "coco.names").read_text().splitlines()
)


def bottle_output() -> np.ndarray:
    output = np.zeros((1, 84, 8400), dtype=np.float32)
    output[0, 0, 0], output[0, 1, 0] = 320.0, 320.0
    output[0, 2, 0], output[0, 3, 0] = 100.0, 100.0
    output[0, 4 + 39, 0] = 0.9
    return output


class FakeSession:
    def __init__(self, output: np.ndarray) -> None:
        self._output = output
        self.feed: dict[str, np.ndarray] = {}

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name="images")]

    def run(
        self, output_names: object, input_feed: dict[str, np.ndarray]
    ) -> list[np.ndarray]:
        self.feed = input_feed
        return [self._output]


def test_infer_letterboxes_normalizes_and_decodes() -> None:
    session = FakeSession(bottle_output())
    backend = OnnxYoloBackend(
        Path("unused.onnx"), COCO_NAMES, input_size=640, session=session
    )
    frame = make_frame(seq=1)  # 64x48 BGR
    [detection] = backend.infer(frame)

    assert detection.class_name == "bottle"
    assert detection.bbox == pytest.approx(
        (0.421875, 0.3958333, 0.578125, 0.6041667), rel=1e-6
    )
    blob = session.feed["images"]
    assert blob.shape == (1, 3, 640, 640)
    assert blob.dtype == np.float32
    assert 0.0 <= float(blob.min()) and float(blob.max()) <= 1.0


def test_infer_returns_no_detections_for_an_empty_output() -> None:
    session = FakeSession(np.zeros((1, 84, 8400), dtype=np.float32))
    backend = OnnxYoloBackend(Path("unused.onnx"), COCO_NAMES, session=session)
    assert backend.infer(make_frame(seq=1)) == []
    backend.close()
