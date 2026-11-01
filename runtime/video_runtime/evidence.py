from collections.abc import Sequence
from pathlib import Path

import cv2

from video_runtime.frame import Frame
from video_runtime.perception import BBox

_JPEG_QUALITY = 85
_BOX_COLOUR = (0, 255, 0)
_REGION_COLOUR = (255, 191, 0)


class EvidenceWriter:
    """Writes annotated keyframes to the backend-shared EVIDENCE_DIR/tmp."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def write(
        self,
        event_id: str,
        frame: Frame,
        *,
        boxes: Sequence[BBox] = (),
        regions: Sequence[BBox] = (),
        label: str | None = None,
    ) -> str:
        image = frame.data.copy()
        height, width = image.shape[:2]
        for region in regions:
            x1, y1, x2, y2 = _pixels(region, width, height)
            cv2.rectangle(image, (x1, y1), (x2, y2), _REGION_COLOUR, 2)
        for bbox in boxes:
            x1, y1, x2, y2 = _pixels(bbox, width, height)
            cv2.rectangle(image, (x1, y1), (x2, y2), _BOX_COLOUR, 2)
        if label:
            cv2.putText(
                image,
                label,
                (4, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                _REGION_COLOUR,
                1,
            )

        path = self._root / "tmp" / f"{event_id}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(
            ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
        )
        if not ok:
            raise RuntimeError(f"failed to encode evidence for event {event_id}")
        path.write_bytes(encoded.tobytes())
        return f"tmp/{event_id}.jpg"


def _pixels(rect: BBox, width: int, height: int) -> tuple[int, int, int, int]:
    return (
        round(rect[0] * width),
        round(rect[1] * height),
        round(rect[2] * width),
        round(rect[3] * height),
    )
