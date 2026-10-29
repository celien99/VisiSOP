from pathlib import Path

import cv2

from video_runtime.frame import Frame
from video_runtime.zones import ZoneHit

_JPEG_QUALITY = 85


class EvidenceWriter:
    """Writes annotated keyframes to the backend-shared EVIDENCE_DIR/tmp."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def write(self, event_id: str, frame: Frame, hit: ZoneHit) -> str:
        image = frame.data.copy()
        height, width = image.shape[:2]
        x1, y1, x2, y2 = _pixels(hit.detection.bbox, width, height)
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        zx1, zy1, zx2, zy2 = _pixels(hit.zone.rect, width, height)
        cv2.rectangle(image, (zx1, zy1), (zx2, zy2), (255, 191, 0), 2)
        cv2.putText(
            image,
            f"{hit.zone.name}: {hit.detection.class_name} {hit.detection.confidence:.2f}",
            (zx1 + 4, max(zy1 + 12, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 191, 0),
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


def _pixels(
    rect: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    return (
        round(rect[0] * width),
        round(rect[1] * height),
        round(rect[2] * width),
        round(rect[3] * height),
    )
