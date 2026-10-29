import cv2
from conftest import make_detection, make_frame

from video_runtime.evidence import EvidenceWriter
from video_runtime.zones import Zone, ZoneHit

PICKUP = Zone(
    "pickup",
    (0.05, 0.15, 0.45, 0.95),
    frozenset({"bottle"}),
    "bottle_in_pickup_zone",
    0.25,
    500,
)


def test_write_creates_tmp_and_returns_the_key(tmp_path) -> None:
    hit = ZoneHit(zone=PICKUP, detection=make_detection())
    key = EvidenceWriter(tmp_path / "evidence").write("evt-1", make_frame(), hit)

    assert key == "tmp/evt-1.jpg"
    path = tmp_path / "evidence" / key
    image = cv2.imread(str(path))
    assert image is not None
    assert image.shape == (48, 64, 3)
