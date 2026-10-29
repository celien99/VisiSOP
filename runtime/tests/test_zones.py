from conftest import make_detection, make_frame

from video_runtime.config import ZoneConfig
from video_runtime.zones import ZoneMapper

PICKUP = ZoneConfig(
    name="pickup",
    rect=(0.0, 0.0, 0.5, 1.0),
    classes=["bottle"],
    event_type="bottle_in_pickup_zone",
)


def test_map_takes_the_best_detection_inside_the_zone() -> None:
    mapper = ZoneMapper([PICKUP])
    detections = [
        make_detection(confidence=0.4, bbox=(0.1, 0.1, 0.3, 0.3)),
        make_detection(confidence=0.8, bbox=(0.2, 0.2, 0.4, 0.4)),
    ]
    [hit] = mapper.map(detections, make_frame())
    assert hit.zone.name == "pickup"
    assert hit.detection.confidence == 0.8


def test_map_ignores_wrong_class_center_and_low_confidence() -> None:
    mapper = ZoneMapper([PICKUP])
    detections = [
        make_detection(class_name="person"),
        make_detection(bbox=(0.6, 0.1, 0.8, 0.3)),
        make_detection(confidence=0.1),
    ]
    assert mapper.map(detections, make_frame()) == []


def test_map_can_hit_two_zones_in_one_frame() -> None:
    mapper = ZoneMapper(
        [
            PICKUP,
            ZoneConfig(
                name="target",
                rect=(0.5, 0.0, 1.0, 1.0),
                classes=["bottle"],
                event_type="bottle_in_target_zone",
            ),
        ]
    )
    hits = mapper.map(
        [
            make_detection(bbox=(0.1, 0.1, 0.3, 0.3)),
            make_detection(bbox=(0.6, 0.1, 0.8, 0.3)),
        ],
        make_frame(),
    )
    assert [hit.zone.name for hit in hits] == ["pickup", "target"]
