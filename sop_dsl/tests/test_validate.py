from pathlib import Path

import pytest
import yaml

from sop_dsl.schema import SOPSpec, SOPStepSpec
from sop_dsl.validate import DSLValidationError, validate_spec

KNOWN = {
    "frame_placed",
    "left_bolt_installed",
    "right_bolt_installed",
    "both_bolts_present",
}


def load(name: str) -> SOPSpec:
    path = Path(__file__).parents[1] / "sop_dsl" / "examples" / name
    return SOPSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _with_missing_skip(step: SOPStepSpec) -> SOPStepSpec:
    if step.skip_if is None:
        return step
    return step.model_copy(
        update={
            "skip_if": step.skip_if.model_copy(
                update={"all_steps_completed": ("missing",)}
            )
        }
    )


def test_examples_validate() -> None:
    for name in ("linear.yaml", "parallel_optional.yaml"):
        validate_spec(load(name), known_event_types=KNOWN)


def test_cycle_is_rejected() -> None:
    spec = load("linear.yaml")
    bad = spec.model_copy(
        update={
            "steps": tuple(
                s.model_copy(update={"depends_on": ("tighten_screw",)})
                if s.key == "place_frame"
                else s
                for s in spec.steps
            )
        }
    )
    with pytest.raises(DSLValidationError) as exc:
        validate_spec(bad)
    assert any(i.code == "CYCLE" for i in exc.value.issues)


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(DSLValidationError) as exc:
        validate_spec(load("linear.yaml"), known_event_types={"other"})
    assert any(i.code == "UNKNOWN_EVENT_TYPE" for i in exc.value.issues)


def test_dangling_skip_reference_is_rejected() -> None:
    spec = load("parallel_optional.yaml")
    bad = spec.model_copy(
        update={"steps": tuple(_with_missing_skip(s) for s in spec.steps)}
    )
    with pytest.raises(DSLValidationError) as exc:
        validate_spec(bad)
    assert any(i.code == "UNKNOWN_STEP_REF" for i in exc.value.issues)
