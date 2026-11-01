import json
from pathlib import Path

from app.domain.sop.compiler import compile_spec
from app.domain.sop.model import StepType
from contracts.catalog import catalog_snapshot
from sop_dsl.schema import SOPSpec
from sop_dsl.validate import validate_spec

SOP_PATH = Path(__file__).parents[1] / "app" / "seed" / "remote_battery.json"


def test_remote_battery_sop_compiles_against_the_catalog() -> None:
    spec = SOPSpec.model_validate(
        json.loads(SOP_PATH.read_text(encoding="utf-8"))
    )
    known = catalog_snapshot().keys()
    validate_spec(spec, known_event_types=known)
    graph = compile_spec(spec, known_event_types=known)
    assert graph.order == (
        "place_remote",
        "insert_batteries",
        "close_lid",
        "verify",
    )
    assert graph.start_steps == ("place_remote",)
    assert graph.steps["verify"].type is StepType.CHECKPOINT


def test_remote_battery_sop_predicates_name_real_attributes() -> None:
    spec = SOPSpec.model_validate(
        json.loads(SOP_PATH.read_text(encoding="utf-8"))
    )
    insert = next(step for step in spec.steps if step.key == "insert_batteries")
    conditions = insert.completion.all
    count = next(
        condition
        for condition in conditions
        if condition.event_type == "batteries_installed"
    )
    assert count.attributes["count"].gte == 2
    assert count.attributes["slots"].eq == 2
