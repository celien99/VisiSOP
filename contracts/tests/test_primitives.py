import pytest
from pydantic import ValidationError

from contracts.primitives import (
    CountThresholdParams,
    ObjectPresentParams,
    PrimitiveSpec,
    UnknownPrimitive,
    get_primitive,
    params_for,
    primitive_snapshot,
    register_primitive,
)


def test_v0_primitives_are_registered() -> None:
    snapshot = primitive_snapshot()
    assert {
        "object_present",
        "object_absent",
        "object_in_zone",
        "object_placed",
        "count_threshold",
        "state_classify",
        "orientation_match",
        "fastening_action",
    } <= set(snapshot)


def test_each_primitive_carries_a_params_model() -> None:
    assert get_primitive("count_threshold").params_model is CountThresholdParams
    assert get_primitive("object_present").params_model is ObjectPresentParams


def test_params_validate_and_reject_extra_fields() -> None:
    params = params_for(
        "count_threshold",
        {
            "object_class": "battery",
            "compartment": "remote",
            "roi": (0.1, 0.2, 0.5, 0.6),
            "slots": 2,
        },
    )
    assert params.model_dump()["slots"] == 2
    with pytest.raises(ValidationError):
        params_for(
            "count_threshold",
            {
                "object_class": "battery",
                "compartment": "remote",
                "roi": (0.1, 0.2, 0.5, 0.6),
                "extra": True,
            },
        )


def test_unknown_primitive_is_rejected() -> None:
    with pytest.raises(UnknownPrimitive):
        get_primitive("not_a_primitive")


def test_snapshot_cannot_be_mutated() -> None:
    snapshot = primitive_snapshot()
    with pytest.raises(TypeError):
        snapshot["x"] = get_primitive("object_present")  # type: ignore[index]  # ty: ignore[invalid-assignment]


def test_custom_primitive_can_be_registered() -> None:
    spec = PrimitiveSpec("test_custom", "1.0", "test only", ObjectPresentParams)
    register_primitive(spec)
    assert get_primitive("test_custom") is spec
