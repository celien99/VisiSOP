from typing import Any

import pytest
from sop_dsl.schema import SOPSpec
from sop_dsl.validate import DSLValidationError

from app.domain.sop.compiler import compile_spec


def spec_from(data: dict[str, Any]) -> SOPSpec:
    return SOPSpec.model_validate(data)


def linear_data() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "sop_key": "s",
        "version": 1,
        "name": "S",
        "steps": [
            {
                "key": "a",
                "name": "A",
                "type": "ACTION",
                "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "a"}]},
            },
            {
                "key": "b",
                "name": "B",
                "type": "ACTION",
                "depends_on": ["a"],
                "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "b"}]},
            },
        ],
    }


def test_linear_order_and_start_steps() -> None:
    graph = compile_spec(spec_from(linear_data()), known_event_types={"a", "b"})
    assert graph.order == ("a", "b")
    assert graph.start_steps == ("a",)


def test_order_is_deterministic_for_parallel_steps() -> None:
    data = linear_data()
    data["steps"] = [
        {
            "key": "z",
            "name": "Z",
            "type": "ACTION",
            "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "z"}]},
        },
        {
            "key": "a",
            "name": "A",
            "type": "ACTION",
            "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "a"}]},
        },
    ]
    graph = compile_spec(spec_from(data), known_event_types={"a", "z"})
    assert graph.order == ("a", "z")


def test_hash_is_stable_and_changes_with_content() -> None:
    spec = spec_from(linear_data())
    assert compile_spec(spec).content_hash == compile_spec(spec).content_hash
    changed = spec.model_copy(update={"version": 2})
    assert compile_spec(changed).content_hash != compile_spec(spec).content_hash


def test_invalid_spec_raises_before_compiling() -> None:
    data = linear_data()
    data["steps"][0]["depends_on"] = ["b"]  # a <-> b cycle
    with pytest.raises(DSLValidationError):
        compile_spec(spec_from(data))
