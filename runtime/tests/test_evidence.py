import cv2
from conftest import make_frame

from video_runtime.evidence import EvidenceWriter


def test_write_creates_tmp_and_returns_the_key(tmp_path) -> None:
    key = EvidenceWriter(tmp_path / "evidence").write(
        "evt-1",
        make_frame(),
        boxes=[(0.1, 0.1, 0.3, 0.3)],
        regions=[(0.0, 0.0, 0.5, 1.0)],
        label="bottle 0.90",
    )

    assert key == "tmp/evt-1.jpg"
    path = tmp_path / "evidence" / key
    image = cv2.imread(str(path))
    assert image is not None
    assert image.shape == (48, 64, 3)
