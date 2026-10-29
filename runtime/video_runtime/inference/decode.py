from collections.abc import Sequence
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from video_runtime.inference.base import Detection

_PAD_VALUE = 114


def letterbox(
    image: NDArray[np.uint8], size: int
) -> tuple[NDArray[np.uint8], float, tuple[float, float]]:
    """Resize the longest side to `size` and pad to a square, keeping aspect."""
    height, width = image.shape[:2]
    scale = size / max(height, width)
    resized = cv2.resize(
        image,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_LINEAR,
    )
    pad_x = (size - resized.shape[1]) // 2
    pad_y = (size - resized.shape[0]) // 2
    padded = np.full((size, size, 3), _PAD_VALUE, dtype=np.uint8)
    padded[pad_y : pad_y + resized.shape[0], pad_x : pad_x + resized.shape[1]] = resized
    return padded, scale, (float(pad_x), float(pad_y))


def nms(
    boxes: NDArray[np.floating], scores: NDArray[np.floating], iou_threshold: float
) -> list[int]:
    """Greedy non-maximum suppression; returns kept indices by descending score."""
    order = np.argsort(scores)[::-1]
    keep: list[int] = []
    while order.size:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        order = rest[_iou(boxes[current], boxes[rest]) <= iou_threshold]
    return keep


def decode_yolo_output(
    output: NDArray[np.float32],
    *,
    scale: float,
    pad: tuple[float, float],
    conf_threshold: float,
    iou_threshold: float,
    class_names: Sequence[str],
    input_size: int = 640,
) -> list[Detection]:
    """Decode a `[1, 4 + classes, N]` YOLO output into normalized detections."""
    expected_rows = 4 + len(class_names)
    if output.ndim != 3 or output.shape[0] != 1 or output.shape[1] != expected_rows:
        raise ValueError(
            f"expected a [1, {expected_rows}, N] YOLO output, got {output.shape}"
        )

    rows = output[0].T
    class_scores = rows[:, 4:]
    class_ids = class_scores.argmax(axis=1)
    confidences = class_scores.max(axis=1)
    keep = confidences >= conf_threshold
    rows, class_ids, confidences = rows[keep], class_ids[keep], confidences[keep]

    cx, cy, width, height = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
    boxes = np.stack(
        [cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2], axis=1
    )
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad[0]) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad[1]) / scale
    boxes[:, [0, 2]] /= (input_size - 2 * pad[0]) / scale
    boxes[:, [1, 3]] /= (input_size - 2 * pad[1]) / scale
    np.clip(boxes, 0.0, 1.0, out=boxes)

    detections: list[Detection] = []
    for class_id in np.unique(class_ids):
        if int(class_id) >= len(class_names):
            continue
        indices = np.nonzero(class_ids == class_id)[0]
        for kept in nms(boxes[indices], confidences[indices], iou_threshold):
            index = indices[kept]
            x1, y1, x2, y2 = (float(value) for value in boxes[index])
            detections.append(
                Detection(
                    class_id=int(class_id),
                    class_name=class_names[int(class_id)],
                    confidence=float(confidences[index]),
                    bbox=(x1, y1, x2, y2),
                )
            )
    return detections


def _iou(
    box: NDArray[np.floating], boxes: NDArray[np.floating]
) -> NDArray[np.floating]:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    intersection = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    box_area = (box[2] - box[0]) * (box[3] - box[1])
    union = areas + box_area - intersection
    return cast(NDArray[np.floating], intersection / np.maximum(union, 1e-9))
