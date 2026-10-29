import json
from pathlib import Path

import contracts.demo  # noqa: F401  (registration side effect)
from app.domain.sop.compiler import compile_spec
from app.domain.sop.model import StepType
from contracts.catalog import catalog_snapshot
from sop_dsl.schema import SOPSpec

SOP_PATH = Path(__file__).parents[1] / "app" / "seed" / "bottle_transfer.json"


def test_demo_sop_compiles_against_the_catalog() -> None:
    spec = SOPSpec.model_validate(json.loads(SOP_PATH.read_text(encoding="utf-8")))
    graph = compile_spec(spec, known_event_types=catalog_snapshot().keys())
    assert graph.order == ("pick_bottle", "place_bottle", "verify_placement")
    assert graph.start_steps == ("pick_bottle",)
    assert graph.steps["verify_placement"].type is StepType.CHECKPOINT
