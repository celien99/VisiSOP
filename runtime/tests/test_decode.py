from pathlib import Path

import numpy as np
import pytest

from video_runtime.inference.decode import decode_yolo_output, letterbox, nms

COCO_NAMES = (
    (Path(__file__).parents[1] / "models" / "coco.names").read_text().splitlines()
)


def test_decode_one_bottle_and_normalizes() -> None:
    output = np.zeros((1, 84, 8400), dtype=np.float32)
    output[0, 0, 0], output[0, 1, 0] = 320.0, 320.0
    output[0, 2, 0], output[0, 3, 0] = 100.0, 100.0
    output[0, 4 + 39, 0] = 0.9  # COCO bottle
    detections = decode_yolo_output(
        output,
        scale=1.0,
        pad=(0.0, 0.0),
        conf_threshold=0.25,
        iou_threshold=0.45,
        class_names=COCO_NAMES,
    )
    assert len(detections) == 1
    assert detections[0].class_name == "bottle"
    assert detections[0].class_id == 39
    assert detections[0].bbox == pytest.approx((0.421875, 0.421875, 0.578125, 0.578125))


def test_decode_undoes_letterbox_padding() -> None:
    output = np.zeros((1, 84, 8400), dtype=np.float32)
    output[0, 0, 0], output[0, 1, 0] = 320.0, 320.0
    output[0, 2, 0], output[0, 3, 0] = 100.0, 100.0
    output[0, 4 + 39, 0] = 0.9
    [detection] = decode_yolo_output(
        output,
        scale=1.0,
        pad=(0.0, 80.0),
        conf_threshold=0.25,
        iou_threshold=0.45,
        class_names=COCO_NAMES,
    )
    assert detection.bbox == pytest.approx(
        (0.421875, 0.3958333, 0.578125, 0.6041667), rel=1e-6
    )


def test_decode_rejects_an_unexpected_shape() -> None:
    with pytest.raises(ValueError):
        decode_yolo_output(
            np.zeros((84, 8400), dtype=np.float32),
            scale=1.0,
            pad=(0.0, 0.0),
            conf_threshold=0.25,
            iou_threshold=0.45,
            class_names=COCO_NAMES,
        )


def test_nms_suppresses_duplicate_boxes() -> None:
    boxes = np.array([[10, 10, 100, 100], [12, 12, 98, 98]], dtype=np.float32)
    scores = np.array([0.9, 0.8], dtype=np.float32)
    assert nms(boxes, scores, 0.45) == [0]


def test_letterbox_pads_to_a_square() -> None:
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    padded, scale, pad = letterbox(image, 320)
    assert padded.shape == (320, 320, 3)
    assert scale == pytest.approx(0.5)
    assert pad == (0.0, 40.0)
    assert padded[0, 0, 0] == 114
