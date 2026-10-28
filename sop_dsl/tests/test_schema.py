from typing import Any

import pytest
from pydantic import ValidationError

from sop_dsl.schema import SOPSpec


def valid_spec(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "sop_key": "seat",
        "version": 1,
        "name": "Seat",
        "steps": [
            {
                "key": "place_frame",
                "name": "Place",
                "type": "ACTION",
                "depends_on": [],
                "timeout_ms": 15000,
                "completion": {
                    "mode": "EVENT_RULE",
                    "all": [
                        {
                            "event_type": "frame_placed",
                            "min_confidence": 0.9,
                            "stable_for_ms": 500,
                        }
                    ],
                },
                "evidence": {"required": True, "kind": "keyframe"},
            }
        ],
    }
    return {**data, **overrides}


def test_valid_spec_parses() -> None:
    spec = SOPSpec.model_validate(valid_spec())
    assert spec.steps[0].key == "place_frame"


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(valid_spec(next=["x"]))


def test_optional_step_requires_skip_if() -> None:
    data = valid_spec()
    data["steps"][0]["required"] = False
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(data)


def test_required_step_cannot_skip() -> None:
    data = valid_spec()
    data["steps"][0]["skip_if"] = {"event_type": "skip_now"}
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(data)


def test_confidence_range_is_enforced() -> None:
    data = valid_spec()
    data["steps"][0]["completion"]["all"][0]["min_confidence"] = 1.5
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(data)


def test_join_policy_accepts_string_and_object() -> None:
    data = valid_spec()
    data["steps"].append(
        {
            "key": "join",
            "name": "Join",
            "type": "CHECKPOINT",
            "depends_on": ["place_frame"],
            "join_policy": "ALL_REQUIRED",
            "completion": {
                "mode": "STATE_RULE",
                "all_steps_completed": ["place_frame"],
            },
        }
    )
    spec = SOPSpec.model_validate(data)
    join_policy = spec.steps[1].join_policy
    assert join_policy is not None
    assert join_policy.type == "ALL_REQUIRED"
    data["steps"][1]["join_policy"] = {"type": "ANY_OF_N", "n": 1}
    spec = SOPSpec.model_validate(data)
    join_policy = spec.steps[1].join_policy
    assert join_policy is not None
    assert join_policy.type == "ANY_OF_N"
    assert join_policy.n == 1


def test_any_of_n_must_be_positive() -> None:
    data = valid_spec()
    data["steps"].append(
        {
            "key": "join",
            "name": "Join",
            "type": "CHECKPOINT",
            "depends_on": ["place_frame"],
            "join_policy": {"type": "ANY_OF_N", "n": 0},
            "completion": {
                "mode": "STATE_RULE",
                "all_steps_completed": ["place_frame"],
            },
        }
    )
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(data)
