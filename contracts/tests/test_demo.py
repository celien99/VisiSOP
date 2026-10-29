import pytest

import contracts.demo  # noqa: F401  (registration side effect)
from contracts.catalog import (
    InvalidAttributes,
    correlation_key_for,
    get_event_type,
    validate_attributes,
)

PICKUP_ATTRS = {
    "object_class": "bottle",
    "zone": "pickup",
    "bbox": [0.1, 0.2, 0.3, 0.4],
}


def test_demo_event_types_are_registered() -> None:
    spec = get_event_type("bottle_in_pickup_zone")
    assert spec.attributes_model.__name__ == "ZoneObjectAttributes"
    assert get_event_type("bottle_in_target_zone").schema_version == "1.0"
    attr = validate_attributes("bottle_in_pickup_zone", PICKUP_ATTRS)
    assert attr.model_dump()["zone"] == "pickup"


def test_demo_correlation_key_is_zone_and_class() -> None:
    key = correlation_key_for(
        "bottle_in_target_zone",
        {"object_class": "bottle", "zone": "target", "bbox": [0.5, 0.2, 0.7, 0.4]},
        station_id="st-01",
    )
    assert key == "st-01:target:bottle"


def test_zone_attributes_are_strict() -> None:
    with pytest.raises(InvalidAttributes):
        validate_attributes(
            "bottle_in_pickup_zone",
            {**PICKUP_ATTRS, "bbox": [0.1, 0.2, 0.3]},
        )
    with pytest.raises(InvalidAttributes):
        validate_attributes(
            "bottle_in_pickup_zone",
            {**PICKUP_ATTRS, "unexpected": 1},
        )
