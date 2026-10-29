from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
import onnxruntime
from numpy.typing import NDArray

from video_runtime.frame import Frame
from video_runtime.inference.base import Detection
from video_runtime.inference.decode import decode_yolo_output, letterbox


class _Session(Protocol):
    def get_inputs(self) -> Sequence[Any]: ...

    def run(
        self, output_names: Any, input_feed: dict[str, NDArray[np.float32]]
    ) -> list[NDArray[np.float32]]: ...


class OnnxYoloBackend:
    """YOLO ONNX inference; the model must not bake NMS in (decode does it)."""

    def __init__(
        self,
        model_path: Path,
        class_names: Sequence[str],
        *,
        input_size: int = 640,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        session: _Session | None = None,
    ) -> None:
        self._class_names = tuple(class_names)
        self._input_size = input_size
        self._conf_threshold = conf_threshold
        self._iou_threshold = iou_threshold
        self._session: _Session = (
            session
            if session is not None
            else onnxruntime.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        )
        self._input_name = str(self._session.get_inputs()[0].name)

    def infer(self, frame: Frame) -> list[Detection]:
        padded, scale, pad = letterbox(frame.data, self._input_size)
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        blob = rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        outputs = self._session.run(None, {self._input_name: blob})
        return decode_yolo_output(
            outputs[0],
            scale=scale,
            pad=pad,
            conf_threshold=self._conf_threshold,
            iou_threshold=self._iou_threshold,
            class_names=self._class_names,
            input_size=self._input_size,
        )

    def close(self) -> None:
        pass
