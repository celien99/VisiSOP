# Contracts + SOP Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现工作包 10（事件契约）与 20（SOP DSL + 领域状态机），使阶段 1 能用模拟事件跑通“事件 → 确定性迁移 → 告警/步骤状态”的闭环。

**Architecture:** 两个纯 Python workspace 包（`contracts/`、`sop_dsl/`）加 backend 领域层（`backend/app/domain/sop/`）。契约只依赖 pydantic；DSL 只做 schema 与静态校验；引擎是纯函数，时间由参数传入，确定性遍历 `graph.order`，不碰数据库、HTTP、模型。

**Tech Stack:** Python 3.14、uv workspace、pydantic 2.13、pytest、hatchling、mypy/ty（strict）、ruff。

**Specs:**
- `docs/implementation/10-contracts.md`
- `docs/implementation/20-domain-sop-engine.md`
- `docs/AI_SOP_Platform_Architecture_v2.0.md` §5–§8、§13.3
- `docs/AI_SOP_Architecture_Design_v1.1.md` §5、§6.4.1–§6.4.3
- `docs/adr/0001-architecture-baseline-review.md`
- `docs/AI_SOP_Perception_Primitive_Catalog_v0.1.md`

## Global Constraints

- 状态名用 v2.0：步骤 `PENDING`/`ACTIVE`/`COMPLETED`/`FAILED`/`SKIPPED`/`TIMED_OUT`/`NEEDS_REVIEW`；执行 `CREATED`/`RUNNING`/`PAUSED`/`COMPLETED`/`ABORTED`/`NEEDS_REVIEW`。不用 `IN_PROGRESS`。
- `backend/app/domain/**` 不得导入 FastAPI、SQLModel、SQLAlchemy、OpenCV、PyTorch、DeepStream。
- `contracts`、`sop_dsl` 的运行时依赖只有 pydantic；`sop_dsl` 的 dev 组加 pyyaml（只用于测试样例）。
- 所有时间必须是带时区的 `AwareDatetime`；引擎不读时钟，`now` 只来自参数。
- 所有输出顺序按 `SOPGraph.order`（编译器产出的确定性拓扑序）；不得依赖 dict/set 遍历顺序。
- DSL 与事件拒绝未知字段；DSL 不允许任意表达式、函数调用、动态代码。
- 新增原因码只允许 `AUTO_SKIP`（对应 20b 自动跳过）；其余沿用 v2.0 §13.3 的封闭枚举。
- 后端覆盖率 ≥ 90%；`mypy`/`ty` strict；ruff 通过。每个任务结束提交一次，格式 `feat:`/`test:`/`chore:`。
- `apply` 不修改输入；带 `event_id` 幂等；迟到事件不回退 `COMPLETED`；`TIMED_OUT` 自动迁移为终态。
- 不在本计划内：`SignalEvent`（等 ADR-0002）、数据库/Alembic/API、真实模型、WebSocket 推送。

## Review Focus

1. **迟到/重复/乱序**：同一 `event_id` 重放不得产生第二次迁移；已 `COMPLETED` 的步骤不得被迟到事件改回。
2. **低置信度/证据不足**：不得自动完成；超时后只能 `TIMED_OUT` 或 `NEEDS_REVIEW`，不得判合格。
3. **多相机冲突**：不得平均置信度；无显式优先级必须 `NEEDS_REVIEW`。
4. **并行/汇合/可选**：汇合节点不得提前解锁，也不得死锁；可选步骤跳过必须留审计原因。
5. **确定性**：同一输入重复调用逐字段相同；打乱 `state.steps` 的插入顺序不影响结果。

---

## Phase A — Contracts（工作包 10）

### Task 1: Bootstrap `contracts` workspace + version + enums

**Files:**
- Create: `contracts/pyproject.toml`
- Create: `contracts/contracts/__init__.py`
- Create: `contracts/contracts/version.py`
- Create: `contracts/contracts/enums.py`
- Create: `contracts/tests/__init__.py`
- Create: `contracts/tests/test_enums.py`
- Modify: `pyproject.toml`（`[tool.uv.workspace].members` 增加 `"contracts"`）
- Modify: `backend/pyproject.toml`（依赖加 `"contracts"`，新增 `[tool.uv.sources] contracts = { workspace = true }`）
- Modify: `backend/Dockerfile`（第一次 `uv sync` 前复制 `contracts/pyproject.toml`，第二次前复制 `contracts/` 源码）
- Modify: `uv.lock`（`uv sync` 生成）

**Interfaces:**
- Produces: `contracts.version.SCHEMA_VERSION: str`, `contracts.version.SUPPORTED_SCHEMA_VERSIONS: frozenset[str]`
- Produces: `contracts.enums.ProcessingResult`, `contracts.enums.CameraRole`, `contracts.enums.MessageType`, `contracts.enums.ReasonCode`（均 `StrEnum`）

- [ ] **Step 1: Write the failing tests**

```python
# contracts/tests/test_enums.py
from contracts.enums import CameraRole, MessageType, ProcessingResult, ReasonCode
from contracts.version import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

def test_schema_version_is_1_0() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS

def test_processing_results_are_closed() -> None:
    assert {r.value for r in ProcessingResult} == {
        "ACCEPTED", "DUPLICATE", "QUARANTINED", "REJECTED"
    }

def test_reason_codes_cover_baseline_and_auto_skip() -> None:
    assert {r.value for r in ReasonCode} == {
        "EXECUTION_AMBIGUOUS", "LOW_CONFIDENCE", "EVIDENCE_MISSING",
        "CAMERA_CONFLICT", "LATE_EVENT", "MODEL_VERSION_MISMATCH",
        "RULE_VERSION_MISMATCH", "MANUAL_SKIP", "AUTO_SKIP", "TIMEOUT",
        "UNEXPECTED_STEP", "OUT_OF_ORDER",
    }

def test_camera_roles_and_message_types() -> None:
    assert CameraRole.OVERVIEW == "overview"
    assert MessageType.ALARM_CREATED == "alarm.created"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package contracts pytest contracts/tests/test_enums.py -v`
Expected: FAIL — package/import not found.

- [ ] **Step 3: Create the workspace package**

`contracts/pyproject.toml`:

```toml
[project]
name = "contracts"
version = "0.1.0"
requires-python = ">=3.14,<4.0"
dependencies = ["pydantic>=2.13.5,<3.0.0"]

[dependency-groups]
dev = [
    "pytest<10.0.0,>=7.4.3",
    "mypy<3.0.0,>=1.8.0",
    "ty>=0.0.25",
    "ruff<1.0.0,>=0.16.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.mypy]
strict = true

[tool.ruff]
target-version = "py314"

[tool.ty.terminal]
error-on-warning = true

[tool.hatch.build.targets.wheel]
packages = ["contracts"]
```

Add `"contracts"` to the root workspace members, add `contracts` to `backend/pyproject.toml` dependencies and `[tool.uv.sources]`. In `backend/Dockerfile`, copy `contracts/pyproject.toml` before the first `uv sync` and `COPY ./contracts /app/contracts` before the second, because uv resolves workspace members even with `--no-install-workspace`. Run `uv sync`.

- [ ] **Step 4: Implement version and enums**

`version.py`: `SCHEMA_VERSION = "1.0"`; `SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})`.

`enums.py`: define the four `StrEnum`s with exactly the values asserted above. `MessageType` includes `ALARM_CREATED`, `ALARM_UPDATED`, `EXECUTION_UPDATED`, `STEP_UPDATED`, `RUNTIME_HEALTH`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --package contracts pytest contracts/tests/test_enums.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add contracts pyproject.toml backend/pyproject.toml backend/Dockerfile uv.lock
git commit -m "feat(contracts): bootstrap the contracts workspace package"
```

---

### Task 2: Event models

**Files:**
- Create: `contracts/contracts/events.py`
- Create: `contracts/tests/test_events.py`
- Modify: `contracts/contracts/__init__.py`

**Interfaces:**
- Produces: `ModelRef(name: str, version: str)`
- Produces: `Observation(schema_version, observation_id, station_id, camera_id, occurred_at, frame_seq, confidence, model, attributes, evidence_refs, execution_id=None)`
- Produces: `VisionEvent(schema_version, event_id, event_type, station_id, camera_id, camera_role, occurred_at, emitted_at, frame_seq, confidence, model, observation_ids, evidence_refs, attributes, correlation_key)`
- Produces: `RoutedSOPEvent(VisionEvent + execution_id, resolution_method, resolved_at, resolver_rule_version, candidate_ids, reason_code)`
- All models: `ConfigDict(extra="forbid", frozen=True)`; `occurred_at`/`emitted_at`/`resolved_at` use `AwareDatetime`; `confidence` in `[0, 1]`; `frame_seq >= 0`.

- [ ] **Step 1: Write the failing tests**

```python
# contracts/tests/test_events.py
from datetime import UTC, datetime
import pytest
from pydantic import ValidationError

from contracts.events import ModelRef, Observation, RoutedSOPEvent, VisionEvent

T = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

def make_event(**overrides):
    data = dict(
        schema_version="1.0", event_id="e-1", event_type="part_placed",
        station_id="station-01", camera_id="camera-left", camera_role="hands",
        occurred_at=T, emitted_at=T, frame_seq=1, confidence=0.9,
        model=ModelRef(name="detector", version="1"), attributes={"part_id": "p1"},
    )
    return VisionEvent(**{**data, **overrides})

def test_valid_event_round_trips_to_json() -> None:
    event = make_event()
    assert VisionEvent.model_validate_json(event.model_dump_json()) == event

def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(occurred_at=datetime(2026, 1, 1, 12, 0))

def test_confidence_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(confidence=1.5)

def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(extra_field=True)

def test_routed_event_requires_execution_id() -> None:
    with pytest.raises(ValidationError):
        RoutedSOPEvent(**make_event().model_dump())

def test_routed_event_requires_resolver_rule_version() -> None:
    with pytest.raises(ValidationError):
        RoutedSOPEvent(
            **make_event().model_dump(), execution_id="exec-1",
            resolution_method="ACTIVE_EXECUTION_WINDOW", resolved_at=T,
            candidate_ids=("exec-1",),
        )

def test_routed_event_carries_resolution_metadata() -> None:
    routed = RoutedSOPEvent(
        **make_event().model_dump(), execution_id="exec-1",
        resolution_method="ACTIVE_EXECUTION_WINDOW", resolved_at=T,
        resolver_rule_version="1", candidate_ids=("exec-1",),
    )
    assert routed.execution_id == "exec-1"

def test_observation_allows_empty_execution_id() -> None:
    observation = Observation(
        schema_version="1.0", observation_id="o-1", station_id="s1",
        camera_id="c1", occurred_at=T, frame_seq=0, confidence=0.9,
        model=ModelRef(name="detector", version="1"),
        attributes={}, evidence_refs=(),
    )
    assert observation.execution_id is None

def test_optional_fields_are_backward_compatible() -> None:
    payload = make_event().model_dump(mode="json")
    payload.pop("camera_role")
    payload.pop("correlation_key")
    assert VisionEvent.model_validate(payload).camera_role is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package contracts pytest contracts/tests/test_events.py -v`
Expected: FAIL — `contracts.events` not found.

- [ ] **Step 3: Implement the models**

Use the exact field names above. `camera_role: str | None = None` and `correlation_key: str | None = None` are optional additions needed by the engine. `RoutedSOPEvent.reason_code` defaults to `None` and `candidate_ids` to `()`; `execution_id` and `resolver_rule_version` are required. Validate `schema_version` against `SUPPORTED_SCHEMA_VERSIONS` with a `field_validator`. `attributes` defaults to `{}` via `Field(default_factory=dict)`; tuples for ID lists.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --package contracts pytest contracts/tests/test_events.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add contracts/contracts/events.py contracts/tests/test_events.py
git commit -m "feat(contracts): add observation and vision event models"
```

---

### Task 3: Event catalog, attribute validation, correlation key

**Files:**
- Create: `contracts/contracts/catalog.py`
- Create: `contracts/tests/test_catalog.py`
- Modify: `contracts/contracts/__init__.py`

**Interfaces:**
- Produces: `EventTypeSpec(event_type: str, attributes_model: type[BaseModel], correlation_key_template: str | None, schema_version: str)`
- Produces: `register_event_type(spec: EventTypeSpec) -> None`（模板含非法占位符时抛 `ValueError`）
- Produces: `get_event_type(event_type: str) -> EventTypeSpec`（未知类型抛 `UnknownEventType`）
- Produces: `validate_attributes(event_type: str, attributes: Mapping[str, Any]) -> BaseModel`（非法 attributes 抛 `InvalidAttributes`）
- Produces: `correlation_key_for(event_type: str, attributes: Mapping[str, Any], *, station_id: str, binding: Mapping[str, str] | None = None) -> str | None`
- Produces: `catalog_snapshot() -> Mapping[str, EventTypeSpec]`
- 默认注册：`frame_placed`、`left_bolt_installed`、`right_bolt_installed`、`both_bolts_present`（空 attributes）、`part_placed`（`part_id: str`, `zone: str`）、`screw_tightened_visual`（`tool_id: str`）、`assembly_present`（空）。

- [ ] **Step 1: Write the failing tests**

```python
# contracts/tests/test_catalog.py
import pytest
from pydantic import BaseModel, ConfigDict

from contracts.catalog import (
    EventTypeSpec, InvalidAttributes, UnknownEventType, catalog_snapshot,
    correlation_key_for, register_event_type, validate_attributes,
)

class _Keyed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    side: str

def test_registered_type_validates_attributes() -> None:
    assert validate_attributes("part_placed", {"part_id": "p1", "zone": "Z1"})
    with pytest.raises(InvalidAttributes):
        validate_attributes("part_placed", {"part_id": "p1"})
    with pytest.raises(InvalidAttributes):
        validate_attributes("part_placed", {"part_id": "p1", "zone": "Z1", "x": 1})

def test_unknown_type_is_rejected() -> None:
    with pytest.raises(UnknownEventType):
        validate_attributes("not_registered", {})

def test_catalog_snapshot_is_read_only() -> None:
    snapshot = catalog_snapshot()
    assert "part_placed" in snapshot
    with pytest.raises(TypeError):
        snapshot["x"] = snapshot["part_placed"]  # type: ignore[index]

def test_correlation_key_uses_only_whitelisted_placeholders() -> None:
    register_event_type(EventTypeSpec(
        event_type="test_keyed", attributes_model=_Keyed,
        correlation_key_template="{station_id}:{binding.workpiece}:{attributes.side}",
    ))
    assert correlation_key_for(
        "test_keyed", {"side": "left"},
        station_id="s1", binding={"workpiece": "w1"},
    ) == "s1:w1:left"

def test_missing_placeholder_yields_no_key() -> None:
    register_event_type(EventTypeSpec(
        event_type="test_missing", attributes_model=_Keyed,
        correlation_key_template="{station_id}:{attributes.workpiece}",
    ))
    assert correlation_key_for("test_missing", {"side": "left"}, station_id="s1") is None

def test_disallowed_placeholder_is_rejected_at_registration() -> None:
    with pytest.raises(ValueError):
        register_event_type(EventTypeSpec(
            event_type="test_bad", attributes_model=_Keyed,
            correlation_key_template="{attributes.side.__class__}",
        ))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package contracts pytest contracts/tests/test_catalog.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the catalog**

Use a module-level `dict[str, EventTypeSpec]`; return `MappingProxyType` from `catalog_snapshot`. `correlation_key_for` parses with `string.Formatter().parse`, accepts only `station_id`, `attributes.<name>`, `binding.<name>`; rejects any other field or format spec; returns `None` if a referenced value is missing. `register_event_type` runs the same parse and raises `ValueError` for a disallowed placeholder, so a bad template fails at import time rather than on the first event. Attribute models use `extra="forbid"`, `frozen=True`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --package contracts pytest contracts/tests/test_catalog.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add contracts/contracts/catalog.py contracts/tests/test_catalog.py contracts/contracts/__init__.py
git commit -m "feat(contracts): add the event catalog and correlation keys"
```

---

### Task 4: WebSocket envelope

**Files:**
- Create: `contracts/contracts/ws.py`
- Create: `contracts/tests/test_ws.py`

**Interfaces:**
- Produces: `WebSocketMessage(schema_version: str, message_id: UUID, type: MessageType, occurred_at: AwareDatetime, station_id: str | None, payload: dict[str, Any])`

- [ ] **Step 1: Write the failing tests**

```python
# contracts/tests/test_ws.py
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from pydantic import ValidationError

from contracts.enums import MessageType
from contracts.ws import WebSocketMessage

T = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

def test_valid_message() -> None:
    msg = WebSocketMessage(
        schema_version="1.0", message_id=uuid4(), type=MessageType.ALARM_CREATED,
        occurred_at=T, station_id="s1", payload={"alarm_id": "a1"},
    )
    assert msg.type is MessageType.ALARM_CREATED

def test_missing_message_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WebSocketMessage(
            schema_version="1.0", type=MessageType.ALARM_CREATED,
            occurred_at=T, station_id=None, payload={},
        )

def test_naive_time_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WebSocketMessage(
            schema_version="1.0", message_id=uuid4(),
            type=MessageType.ALARM_CREATED, occurred_at=datetime(2026, 1, 1),
            station_id=None, payload={},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package contracts pytest contracts/tests/test_ws.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `WebSocketMessage`**

`ConfigDict(extra="forbid", frozen=True)`; validate `schema_version` against `SUPPORTED_SCHEMA_VERSIONS`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --package contracts pytest contracts/tests/test_ws.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add contracts/contracts/ws.py contracts/tests/test_ws.py
git commit -m "feat(contracts): add the websocket message envelope"
```

---

## Phase B — SOP DSL（工作包 20，静态层）

### Task 5: `sop_dsl` workspace + schema models

**Files:**
- Create: `sop_dsl/pyproject.toml`
- Create: `sop_dsl/sop_dsl/__init__.py`
- Create: `sop_dsl/sop_dsl/schema.py`
- Create: `sop_dsl/tests/__init__.py`
- Create: `sop_dsl/tests/test_schema.py`
- Modify: `pyproject.toml`（workspace 加 `"sop_dsl"`）
- Modify: `backend/pyproject.toml`（依赖加 `"sop_dsl"` + workspace source）
- Modify: `backend/Dockerfile`（同 Task 1，补 `sop_dsl` 的 manifest 与源码）
- Modify: `uv.lock`

**Interfaces:**
- Produces: `StepType(ACTION, CHECKPOINT)`, `CompletionMode(EVENT_RULE, STATE_RULE)`
- Produces: `EventCondition(event_type, min_confidence, stable_for_ms, within_ms, source_camera_role)`
- Produces: `EventRuleCompletion(mode="EVENT_RULE", all, any, not_)`
- Produces: `StateRuleCompletion(mode="STATE_RULE", all_steps_completed, any_steps_completed)`
- Produces: `CompletionSpec = Annotated[EventRuleCompletion | StateRuleCompletion, Field(discriminator="mode")]`
- Produces: `JoinPolicy(type, n)` accepting `"ALL_REQUIRED"` or `{"type": "ANY_OF_N", "n": N}`
- Produces: `SkipIf(all_steps_completed, event_type)`, `EvidenceSpec(required, kind)`, `FailureRule(event_type, reason_code)`
- Produces: `SOPStepSpec` and `SOPSpec`
- 所有模型 `extra="forbid", frozen=True`；`SOPSpec.steps` 用 tuple。

- [ ] **Step 1: Write the failing tests**

```python
# sop_dsl/tests/test_schema.py
import pytest
from pydantic import ValidationError

from sop_dsl.schema import SOPSpec

def valid_spec(**overrides):
    data = {
        "schema_version": "1.0", "sop_key": "seat", "version": 1, "name": "Seat",
        "steps": [{
            "key": "place_frame", "name": "Place", "type": "ACTION",
            "depends_on": [], "timeout_ms": 15000,
            "completion": {"mode": "EVENT_RULE", "all": [
                {"event_type": "frame_placed", "min_confidence": 0.9,
                 "stable_for_ms": 500}
            ]},
            "evidence": {"required": True, "kind": "keyframe"},
        }],
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

def test_confidence_range_is_enforced() -> None:
    data = valid_spec()
    data["steps"][0]["completion"]["all"][0]["min_confidence"] = 1.5
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(data)

def test_join_policy_accepts_string_and_object() -> None:
    data = valid_spec()
    data["steps"].append({
        "key": "join", "name": "Join", "type": "CHECKPOINT",
        "depends_on": ["place_frame"], "join_policy": "ALL_REQUIRED",
        "completion": {"mode": "STATE_RULE",
                       "all_steps_completed": ["place_frame"]},
    })
    spec = SOPSpec.model_validate(data)
    assert spec.steps[1].join_policy.type == "ALL_REQUIRED"
    data["steps"][1]["join_policy"] = {"type": "ANY_OF_N", "n": 1}
    spec = SOPSpec.model_validate(data)
    assert spec.steps[1].join_policy.type == "ANY_OF_N"
    assert spec.steps[1].join_policy.n == 1

def test_any_of_n_must_be_positive() -> None:
    data = valid_spec()
    data["steps"].append({
        "key": "join", "name": "Join", "type": "CHECKPOINT",
        "depends_on": ["place_frame"],
        "join_policy": {"type": "ANY_OF_N", "n": 0},
        "completion": {"mode": "STATE_RULE",
                       "all_steps_completed": ["place_frame"]},
    })
    with pytest.raises(ValidationError):
        SOPSpec.model_validate(data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package sop_dsl pytest sop_dsl/tests/test_schema.py -v`
Expected: FAIL.

- [ ] **Step 3: Create the package and implement the schema**

`join_policy` normalization: a `model_validator(mode="before")` turns `"ALL_REQUIRED"` into `{"type": "ALL_REQUIRED"}`. `SkipIf` requires exactly one of `all_steps_completed` (non-empty tuple) or `event_type`. `SOPStepSpec` rejects `required=False` without `skip_if`, and `join_policy` with empty `depends_on`. `FailureRule.reason_code` is validated against `contracts.enums.ReasonCode` (add `contracts` to `sop_dsl` dependencies). Create `sop_dsl/pyproject.toml` with the same dev group and `mypy`/`ruff`/`ty` strict sections as `contracts/pyproject.toml`; add `sop_dsl` to `backend/pyproject.toml` and to `backend/Dockerfile` the same way as `contracts` in Task 1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --package sop_dsl pytest sop_dsl/tests/test_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sop_dsl pyproject.toml backend/pyproject.toml backend/Dockerfile uv.lock
git commit -m "feat(sop-dsl): add the versioned DSL v1 schema"
```

---

### Task 6: Static validation + examples

**Files:**
- Create: `sop_dsl/sop_dsl/validate.py`
- Create: `sop_dsl/sop_dsl/examples/linear.yaml`
- Create: `sop_dsl/sop_dsl/examples/parallel_optional.yaml`
- Create: `sop_dsl/tests/test_validate.py`
- Modify: `sop_dsl/pyproject.toml`（dev 加 `pyyaml>=6.0`）

**Interfaces:**
- Produces: `ValidationIssue(code: str, message: str, step_key: str | None)`
- Produces: `DSLValidationError(issues: list[ValidationIssue])`
- Produces: `validate_spec(spec: SOPSpec, *, known_event_types: Collection[str] | None = None) -> None`
- Checks: duplicate keys；依赖存在；无自依赖；DAG 无环；至少一个起点；join 节点必须有依赖且 `completion` 必须是 `STATE_RULE`；`ANY_OF_N.n <= len(depends_on)`；`skip_if` 引用存在；`skip_if.event_type` / `failure.event_type` / `EventCondition.event_type` 在 `known_event_types` 内（提供时）；所有问题一次性收集后抛错。

- [ ] **Step 1: Write the failing tests**

```python
# sop_dsl/tests/test_validate.py
from pathlib import Path
import pytest
import yaml

from sop_dsl.schema import SOPSpec
from sop_dsl.validate import DSLValidationError, validate_spec

KNOWN = {"frame_placed", "left_bolt_installed", "right_bolt_installed",
         "both_bolts_present"}

def load(name: str) -> SOPSpec:
    path = Path(__file__).parents[1] / "sop_dsl" / "examples" / name
    return SOPSpec.model_validate(yaml.safe_load(path.read_text()))

def test_examples_validate() -> None:
    for name in ("linear.yaml", "parallel_optional.yaml"):
        validate_spec(load(name), known_event_types=KNOWN)

def test_cycle_is_rejected() -> None:
    spec = load("linear.yaml")
    bad = spec.model_copy(update={"steps": tuple(
        s.model_copy(update={"depends_on": ("tighten_screw",)})
        if s.key == "place_frame" else s for s in spec.steps
    )})
    with pytest.raises(DSLValidationError) as exc:
        validate_spec(bad)
    assert any(i.code == "CYCLE" for i in exc.value.issues)

def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(DSLValidationError) as exc:
        validate_spec(load("linear.yaml"), known_event_types={"other"})
    assert any(i.code == "UNKNOWN_EVENT_TYPE" for i in exc.value.issues)

def test_dangling_skip_reference_is_rejected() -> None:
    spec = load("parallel_optional.yaml")
    bad = spec.model_copy(update={"steps": tuple(
        s.model_copy(update={"skip_if": s.skip_if.model_copy(
            update={"all_steps_completed": ("missing",)}
        )}) if s.skip_if else s for s in spec.steps
    )})
    with pytest.raises(DSLValidationError) as exc:
        validate_spec(bad)
    assert any(i.code == "UNKNOWN_STEP_REF" for i in exc.value.issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package sop_dsl pytest sop_dsl/tests/test_validate.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement validation and examples**

`linear.yaml` is the baseline §6.1 example (four steps, `depends_on`, `join_policy: "ALL_REQUIRED"`). `parallel_optional.yaml` adds a `required: false` step with `skip_if: {all_steps_completed: [...]}` and an `ANY_OF_N` join. Collect issues in a list; raise once. Use Kahn's algorithm for cycle detection; tie-break by key only for deterministic messages.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --package sop_dsl pytest sop_dsl/tests/test_validate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sop_dsl/sop_dsl/validate.py sop_dsl/sop_dsl/examples sop_dsl/tests/test_validate.py sop_dsl/pyproject.toml
git commit -m "feat(sop-dsl): add static validation and examples"
```

---

## Phase C — Domain engine（工作包 20，执行层）

### Task 7: Domain model

**Files:**
- Create: `backend/app/domain/__init__.py`
- Create: `backend/app/domain/sop/__init__.py`
- Create: `backend/app/domain/sop/model.py`
- Create: `backend/tests/domain/__init__.py`
- Create: `backend/tests/domain/sop/__init__.py`
- Create: `backend/tests/domain/sop/test_model.py`

**Interfaces:**
- Produces: `StepStatus`, `ExecutionStatus`（值见 Global Constraints）
- Produces: `MatchedEvent(event_id, event_type, confidence, occurred_at, camera_id, camera_role, correlation_key, accepted)`
- Produces: `StepState(key, status, activated_at, deadline_at, matched_events, reason_code, skipped_reason)`
- Produces: `ExecutionState(execution_id, status, steps, started_at, paused_at)`
- Produces: `CompiledStep(key, name, type, required, depends_on, timeout_ms, completion, evidence, join_policy, skip_if, failure)`
- Produces: `SOPGraph(sop_key, version, dsl_schema_version, content_hash, steps, order, start_steps)`
- Produces: `StepTransition(step_key, from_status, to_status, reason_code, matched_event_ids, detail)`
- Produces: `ExecutionTransition(from_status, to_status, reason_code)`
- Produces: `EvidenceUpdate(step_key, event: MatchedEvent)`
- Produces: `AlarmIntent(category, severity, reason_code, step_key, source_event_id, message)`
- Produces: `TransitionResult(step_transitions, evidence_updates, execution_transition, alarms, processing_result, reason_code, detail, rule_version, dsl_version)`
- 全部 `@dataclass(frozen=True)`；`steps` 用 `MappingProxyType`，集合字段用 tuple。
- `model.py` 可导入 `contracts.enums`、`contracts.events`、`sop_dsl.schema`；不得导入其余后端模块。

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_model.py
import dataclasses
import pytest

from app.domain.sop.model import (
    AlarmIntent, ExecutionState, ExecutionStatus, MatchedEvent, SOPGraph,
    StepState, StepStatus, TransitionResult,
)
from contracts.enums import ProcessingResult, ReasonCode

def test_step_status_values() -> None:
    assert StepStatus.ACTIVE == "ACTIVE"
    assert ExecutionStatus.NEEDS_REVIEW == "NEEDS_REVIEW"

def test_models_are_frozen() -> None:
    state = StepState(key="a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.status = StepStatus.COMPLETED  # type: ignore[misc]

def test_transition_result_defaults_to_accepted() -> None:
    result = TransitionResult()
    assert result.processing_result is ProcessingResult.ACCEPTED
    assert result.step_transitions == ()

def test_alarm_carries_reason_code() -> None:
    alarm = AlarmIntent(category="PROCESS_COMPLIANCE", severity="HIGH",
                        reason_code=ReasonCode.TIMEOUT, step_key="a")
    assert alarm.reason_code is ReasonCode.TIMEOUT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_model.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the model dataclasses**

`SOPGraph.steps` is `Mapping[str, CompiledStep]`; the compiler wraps it in `MappingProxyType`. `TransitionResult` defaults are empty tuples / `None` / `ProcessingResult.ACCEPTED`. `reason_code` uses `ReasonCode | None`; `StepState.skipped_reason: str | None`; `StepTransition.detail: str | None` carries the audit string for skips and late events. `StepState` defaults: `status=PENDING`, `activated_at=None`, `deadline_at=None`, `matched_events=()`, `reason_code=None`, `skipped_reason=None`. `AlarmIntent` defaults: `step_key=None`, `source_event_id=None`, `message=""`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain backend/tests/domain
git commit -m "feat(domain): add the SOP execution model"
```

---

### Task 8: Compiler

**Files:**
- Create: `backend/app/domain/sop/compiler.py`
- Create: `backend/tests/domain/sop/test_compiler.py`

**Interfaces:**
- Produces: `compile_spec(spec: SOPSpec, *, known_event_types: Collection[str] | None = None) -> SOPGraph`
- Behavior: call `validate_spec`; build `CompiledStep` for every step; topological order with Kahn, ready set sorted by key; `start_steps` sorted; `content_hash = sha256(spec.model_dump_json())`; `steps` wrapped in `MappingProxyType`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_compiler.py
import pytest

from app.domain.sop.compiler import compile_spec
from sop_dsl.schema import SOPSpec
from sop_dsl.validate import DSLValidationError

def spec_from(data: dict) -> SOPSpec:
    return SOPSpec.model_validate(data)

def linear_data() -> dict:
    return {
        "schema_version": "1.0", "sop_key": "s", "version": 1, "name": "S",
        "steps": [
            {"key": "a", "name": "A", "type": "ACTION",
             "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "a"}]}},
            {"key": "b", "name": "B", "type": "ACTION", "depends_on": ["a"],
             "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "b"}]}},
        ],
    }

def test_linear_order_and_start_steps() -> None:
    graph = compile_spec(spec_from(linear_data()), known_event_types={"a", "b"})
    assert graph.order == ("a", "b")
    assert graph.start_steps == ("a",)

def test_order_is_deterministic_for_parallel_steps() -> None:
    data = linear_data()
    data["steps"] = [
        {"key": "z", "name": "Z", "type": "ACTION",
         "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "z"}]}},
        {"key": "a", "name": "A", "type": "ACTION",
         "completion": {"mode": "EVENT_RULE", "all": [{"event_type": "a"}]}},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_compiler.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `compile_spec`**

Reuse `validate_spec`; do not duplicate validation. Kahn's algorithm with a sorted ready list. Preserve `depends_on` as tuple. `content_hash` uses UTF-8 and hex digest.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_compiler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/compiler.py backend/tests/domain/sop/test_compiler.py
git commit -m "feat(domain): compile the SOP DSL into an immutable graph"
```

---

### Task 9: Initial state + activation + ALL completion

**Files:**
- Create: `backend/app/domain/sop/engine.py`
- Create: `backend/tests/domain/sop/conftest.py`
- Create: `backend/tests/domain/sop/test_engine_activation.py`

**Interfaces:**
- Produces: `initial_state(graph: SOPGraph, execution_id: str, now: datetime) -> ExecutionState`
- Produces: `apply(graph: SOPGraph, state: ExecutionState, event: RoutedSOPEvent, now: datetime) -> TransitionResult`
- Behavior:
  - `initial_state`: start steps `ACTIVE` with `activated_at=now`, `deadline_at=now+timeout_ms`; other steps `PENDING`; execution `RUNNING`, `started_at=now`.
  - `apply`: terminal execution → no transitions; duplicate `event_id` → `DUPLICATE`; event for a not-ready step → `OUT_OF_ORDER` alarm; unregistered event type → `UNEXPECTED_STEP` alarm; `ALL` conditions with `min_confidence`; atomic `PENDING → COMPLETED` when the step is dependency-ready and the event completes it; after any change, activate newly ready steps.
  - Iterate `graph.order`, never dict order.

**Fixture conventions (`conftest.py`):**

- `T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)`. Test modules import it explicitly; the snippets below omit the `timedelta`/`T0` imports for brevity.
- `step_spec(key, *, depends_on=(), timeout_ms=1000, required=True, completion=None, skip_if=None, join_policy=None, failure=None) -> dict[str, Any]`
- `event_rule(event_type, *, min_confidence=0.9, stable_for_ms=0, within_ms=None, source_camera_role=None) -> dict[str, Any]`
- `make_spec(steps, *, sop_key="s", version=1) -> SOPSpec`
- `make_graph(steps, *, known=None) -> SOPGraph`
- `make_event(event_type, *, event_id="e-1", confidence=0.95, occurred_at=T0, camera_role=None, attributes=None) -> RoutedSOPEvent`
- `make_state(graph, *, status=ExecutionStatus.RUNNING, steps=None, execution_id="e") -> ExecutionState` — `steps` maps key → `StepState`; defaults to `initial_state`.
- `advance(graph, state, events, now=T0) -> ExecutionState` — test-only fold: call `apply` for each event in order, apply the returned transitions and evidence updates to new `StepState`s (copy `detail` into `skipped_reason` for `AUTO_SKIP`), and return the new state. It never calls `timed_out`.
- `graph_ab`: step `a` (no deps, 1000ms, `EVENT_RULE all [a_done]`), step `b` (depends `a`, `EVENT_RULE all [b_done]`).
- `state_with_a_done`: `advance(graph_ab, initial_state(graph_ab, "e", T0), [make_event("a_done")])`.
- `state_with_a_completed`: `make_state(graph_ab, steps={"a": StepState(key="a", status=COMPLETED), "b": StepState(key="b")})` — deliberately leaves `b` `PENDING`.
- `state_with_low_confidence`: `advance(graph_ab, initial_state(graph_ab, "e", T0), [make_event("a_done", confidence=0.5)])`.
- `state_with_a_timed_out`: `make_state(graph_ab, steps={"a": StepState(key="a", status=TIMED_OUT), "b": StepState(key="b")})` — no matched events.
- `state_completed`: both steps `COMPLETED`, execution `COMPLETED`.
- `state_all_completed`: both steps `COMPLETED`, execution `RUNNING`.
- `state_with_a_failed`: `a` `FAILED`, `b` `PENDING`, execution `RUNNING`.
- Tests that add a second event to a state that already contains one pass a new `event_id` (`"e-2"`, …); the default `e-1` is assumed unused.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_activation.py
from app.domain.sop.engine import apply, initial_state
from app.domain.sop.model import StepStatus
from contracts.enums import ProcessingResult, ReasonCode

def test_initial_state_activates_start_steps(graph_ab) -> None:
    state = initial_state(graph_ab, "exec-1", T0)
    assert state.steps["a"].status is StepStatus.ACTIVE
    assert state.steps["b"].status is StepStatus.PENDING
    assert state.steps["a"].deadline_at is not None

def test_event_completes_active_step_and_activates_next(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0),
                   make_event("a_done"), T0 + timedelta(seconds=1))
    transitions = {t.step_key: t for t in result.step_transitions}
    assert transitions["a"].to_status is StepStatus.COMPLETED
    assert transitions["b"].to_status is StepStatus.ACTIVE

def test_atomic_pending_to_completed(graph_ab, state_with_a_completed) -> None:
    # state_with_a_completed keeps b PENDING (stale state); event completes it
    result = apply(graph_ab, state_with_a_completed, make_event("b_done"), T0)
    assert result.step_transitions[0].from_status is StepStatus.PENDING
    assert result.step_transitions[0].to_status is StepStatus.COMPLETED

def test_out_of_order_event_does_not_advance(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0),
                   make_event("b_done"), T0)
    assert result.step_transitions == ()
    assert result.alarms[0].reason_code is ReasonCode.OUT_OF_ORDER

def test_unknown_event_type_is_unexpected(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0),
                   make_event("mystery"), T0)
    assert result.alarms[0].reason_code is ReasonCode.UNEXPECTED_STEP

def test_low_confidence_does_not_complete(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0),
                   make_event("a_done", confidence=0.5), T0)
    assert all(t.to_status is not StepStatus.COMPLETED
               for t in result.step_transitions)
    assert result.evidence_updates[0].event.accepted is False

def test_same_event_id_is_duplicate(graph_ab, state_with_a_done) -> None:
    result = apply(graph_ab, state_with_a_done, make_event("a_done"), T0)
    assert result.processing_result is ProcessingResult.DUPLICATE
    assert result.step_transitions == ()

def test_apply_is_deterministic(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    event = make_event("a_done")
    assert apply(graph_ab, state, event, T0) == apply(graph_ab, state, event, T0)

def test_apply_does_not_mutate_input(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    snapshot = copy.deepcopy(state)
    apply(graph_ab, state, make_event("a_done"), T0)
    assert state == snapshot
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_activation.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `initial_state` and `apply` (20a core)**

Keep a private `_settle(graph, steps, now)` that loops in `graph.order` until no change: activate dependency-ready `PENDING` steps; do not evaluate `STATE_RULE` or joins yet. `apply` records `EvidenceUpdate` for every event that reaches a step, with `accepted` set by type/confidence/role filters. `OUT_OF_ORDER` when a target step's deps are not satisfied; `UNEXPECTED_STEP` when no step references the event type.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_activation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/tests/domain/sop
git commit -m "feat(domain): add activation and event-rule completion"
```

---

### Task 10: `any`/`not`, `stable_for_ms`, `within_ms`, camera role

**Files:**
- Modify: `backend/app/domain/sop/engine.py`
- Create: `backend/tests/domain/sop/test_engine_rules.py`

**Interfaces:**
- Consumes: Task 9 `apply`/`initial_state` and `StepState.matched_events`.
- Behavior:
  - `all`: every condition satisfied.
  - `any`: at least one condition satisfied.
  - `not`: none of the conditions satisfied (a matching event blocks completion).
  - `stable_for_ms`: earliest-to-latest `occurred_at` span of accepted matching events must be ≥ the value; a single event satisfies only `stable_for_ms=0`.
  - `within_ms`: accepted matching events must have `occurred_at <= activated_at + within_ms`.
  - `source_camera_role`: matching event's `camera_role` must equal the condition.
  - Any rule failure leaves the step `ACTIVE`; no alarm until timeout.

**Fixtures used here:** `any_graph` = one start step `a` with `EVENT_RULE any [a_done, b_done]`; `not_graph` = one start step `a` with `EVENT_RULE all [present]`, `not` [`part_removed`]; `stable_graph` = one start step `a` with `EVENT_RULE all [present]` and `stable_for_ms=500`; `state_with_first_event` = `advance(stable_graph, initial_state(stable_graph, "e", T0), [make_event("present")])`; `within_graph` = one start step `a` with `within_ms=500`; `role_graph` = one start step `a` with `source_camera_role="overview"`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_rules.py

def test_any_rule_completes_on_one_of_two_events(any_graph) -> None:
    result = apply(any_graph, initial_state(any_graph, "e", T0),
                   make_event("b_done"), T0 + timedelta(seconds=1))
    assert result.step_transitions[0].to_status is StepStatus.COMPLETED

def test_not_rule_blocks_completion(not_graph) -> None:
    state = initial_state(not_graph, "e", T0)
    blocked = apply(not_graph, state, make_event("part_removed"), T0)
    assert all(t.to_status is not StepStatus.COMPLETED
               for t in blocked.step_transitions)

def test_stable_for_ms_needs_a_span(stable_graph, state_with_first_event) -> None:
    early = apply(stable_graph, state_with_first_event,
                  make_event("present", event_id="e-2",
                             occurred_at=T0 + timedelta(milliseconds=100)),
                  T0 + timedelta(milliseconds=100))
    assert all(t.to_status is not StepStatus.COMPLETED
               for t in early.step_transitions)
    late = apply(stable_graph, state_with_first_event,
                 make_event("present", event_id="e-2",
                            occurred_at=T0 + timedelta(milliseconds=600)),
                 T0 + timedelta(milliseconds=600))
    assert late.step_transitions[0].to_status is StepStatus.COMPLETED

def test_within_ms_rejects_late_evidence(within_graph) -> None:
    result = apply(within_graph, initial_state(within_graph, "e", T0),
                   make_event("present", occurred_at=T0 + timedelta(milliseconds=600)),
                   T0 + timedelta(milliseconds=600))
    assert all(t.to_status is not StepStatus.COMPLETED
               for t in result.step_transitions)

def test_source_camera_role_is_enforced(role_graph) -> None:
    wrong = apply(role_graph, initial_state(role_graph, "e", T0),
                  make_event("present", camera_role="hands"), T0)
    assert all(t.to_status is not StepStatus.COMPLETED
               for t in wrong.step_transitions)
    right = apply(role_graph, initial_state(role_graph, "e", T0),
                  make_event("present", camera_role="overview"), T0)
    assert right.step_transitions[0].to_status is StepStatus.COMPLETED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_rules.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement condition evaluation**

Add `_condition_matches(condition, events, activated_at) -> bool` and `_rule_satisfied(completion, events, activated_at) -> bool`. Only `accepted` events count. `not` is satisfied when no accepted event matches its conditions. Keep `EvidenceUpdate` for rejected events.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_rules.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/tests/domain/sop/test_engine_rules.py
git commit -m "feat(domain): evaluate compound event rules and evidence windows"
```

---

### Task 11: Timeouts

**Files:**
- Modify: `backend/app/domain/sop/engine.py`
- Create: `backend/tests/domain/sop/test_engine_timeout.py`

**Interfaces:**
- Produces: `timed_out(graph: SOPGraph, state: ExecutionState, now: datetime) -> list[StepTransition]`
- Behavior:
  - Only `ACTIVE` steps with `deadline_at is not None and deadline_at <= now`.
  - Execution `PAUSED` → no transitions.
  - If any matched event was rejected (low confidence) → `NEEDS_REVIEW` with `LOW_CONFIDENCE`.
  - Otherwise → `TIMED_OUT` with `TIMEOUT`.
  - After timeouts, run the same settle pass and include downstream activations in the returned list.
  - Deterministic `graph.order`.
  - Timeout alarms are package 30's job: this task returns transitions only.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_timeout.py

def test_timeout_marks_step_timed_out(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)  # a timeout 1000ms
    transitions = timed_out(graph_ab, state, T0 + timedelta(milliseconds=1001))
    assert transitions[0].step_key == "a"
    assert transitions[0].to_status is StepStatus.TIMED_OUT
    assert transitions[0].reason_code is ReasonCode.TIMEOUT

def test_no_timeout_before_deadline(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    assert timed_out(graph_ab, state, T0 + timedelta(milliseconds=999)) == []

def test_paused_execution_does_not_timeout(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    paused = dataclasses.replace(state, status=ExecutionStatus.PAUSED)
    assert timed_out(graph_ab, paused, T0 + timedelta(seconds=10)) == []

def test_low_confidence_timeout_goes_to_review(graph_ab, state_with_low_confidence) -> None:
    transitions = timed_out(graph_ab, state_with_low_confidence,
                            T0 + timedelta(milliseconds=1001))
    assert transitions[0].to_status is StepStatus.NEEDS_REVIEW
    assert transitions[0].reason_code is ReasonCode.LOW_CONFIDENCE

def test_late_event_after_timeout_does_not_complete(graph_ab, state_with_a_timed_out) -> None:
    result = apply(graph_ab, state_with_a_timed_out, make_event("a_done"), T0)
    assert all(t.to_status is not StepStatus.COMPLETED
               for t in result.step_transitions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_timeout.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `timed_out`**

Reuse `_settle`; do not read the clock. `deadline_at <= now` is inclusive. Timeout is terminal for automatic transitions (A12).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_timeout.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/tests/domain/sop/test_engine_timeout.py
git commit -m "feat(domain): add deterministic timeout transitions"
```

---

### Task 12: Duplicate, late, and ordering invariants

**Files:**
- Modify: `backend/app/domain/sop/engine.py`
- Create: `backend/tests/domain/sop/test_engine_invariants.py`

**Interfaces:**
- Behavior:
  - Duplicate `event_id` anywhere in `state.steps[*].matched_events` → `ProcessingResult.DUPLICATE`, no transitions.
  - Execution `COMPLETED`/`ABORTED` → no transitions, `reason_code=LATE_EVENT`, detail `"execution_terminal"`.
  - Event for a `COMPLETED` step → evidence update only; status unchanged.
  - Event for a `TIMED_OUT` step that would satisfy completion → `NEEDS_REVIEW` with `LATE_EVENT`; never back to `COMPLETED`.
  - Results are identical when `state.steps` insertion order is reversed.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_invariants.py

def test_late_event_does_not_roll_back_completed(graph_ab, state_with_a_done) -> None:
    result = apply(graph_ab, state_with_a_done, make_event("a_done", event_id="e-2"), T0)
    assert all(t.step_key != "a" or t.from_status != StepStatus.COMPLETED
               for t in result.step_transitions)

def test_late_event_after_timeout_goes_to_review(graph_ab, state_with_a_timed_out) -> None:
    result = apply(graph_ab, state_with_a_timed_out,
                   make_event("a_done", event_id="e-3"), T0)
    transition = next(t for t in result.step_transitions if t.step_key == "a")
    assert transition.to_status is StepStatus.NEEDS_REVIEW
    assert transition.reason_code is ReasonCode.LATE_EVENT

def test_terminal_execution_ignores_events(graph_ab, state_completed) -> None:
    result = apply(graph_ab, state_completed, make_event("a_done"), T0)
    assert result.step_transitions == ()
    assert result.reason_code is ReasonCode.LATE_EVENT

def test_step_mapping_order_does_not_change_result(graph_ab) -> None:
    state = initial_state(graph_ab, "e", T0)
    reversed_state = dataclasses.replace(
        state, steps=dict(reversed(list(state.steps.items()))))
    event = make_event("a_done")
    assert apply(graph_ab, state, event, T0) == apply(graph_ab, reversed_state, event, T0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_invariants.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the invariants**

Check duplicates before target selection. Check terminal execution first. Emit transitions in `graph.order`. Never transition down from `COMPLETED`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_invariants.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/tests/domain/sop/test_engine_invariants.py
git commit -m "feat(domain): enforce duplicate and late-event invariants"
```

---

### Task 13: Execution status, failure rules, alarms

**Files:**
- Modify: `backend/app/domain/sop/engine.py`
- Modify: `backend/app/domain/sop/model.py`（如缺 `derive_execution_status` 所需字段）
- Create: `backend/tests/domain/sop/test_engine_execution.py`

**Interfaces:**
- Produces: `derive_execution_status(graph: SOPGraph, steps: Mapping[str, StepState], current: ExecutionStatus) -> ExecutionStatus`
- Behavior:
  - Any `NEEDS_REVIEW` step → `NEEDS_REVIEW`.
  - Required step `FAILED` or `TIMED_OUT` → `NEEDS_REVIEW`.
  - All required steps `COMPLETED`/`SKIPPED` and all steps terminal → `COMPLETED`.
  - Otherwise keep `RUNNING` (or current).
  - `failure` rule: matching event on an `ACTIVE` step → `FAILED` with the rule's `reason_code`.
  - Alarms: `OUT_OF_ORDER`/`UNEXPECTED_STEP` → `PROCESS_COMPLIANCE`/`HIGH`; timeout → `PROCESS_COMPLIANCE`/`HIGH`; low confidence → `VISION_QUALITY`/`MEDIUM`.

**Fixtures used here:** `failure_graph` = one start step `a` with `EVENT_RULE all [a_done]` and `failure {event_type:"bad_part", reason_code:"EVIDENCE_MISSING"}`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_execution.py

def test_execution_completes_when_all_steps_terminal(graph_ab, state_all_completed) -> None:
    assert derive_execution_status(graph_ab, state_all_completed.steps,
                                   ExecutionStatus.RUNNING) is ExecutionStatus.COMPLETED

def test_failed_required_step_blocks_completion(graph_ab, state_with_a_failed) -> None:
    assert derive_execution_status(graph_ab, state_with_a_failed.steps,
                                   ExecutionStatus.RUNNING) is ExecutionStatus.NEEDS_REVIEW

def test_failure_rule_marks_step_failed(failure_graph) -> None:
    result = apply(failure_graph, initial_state(failure_graph, "e", T0),
                   make_event("bad_part"), T0)
    assert result.step_transitions[0].to_status is StepStatus.FAILED
    assert result.step_transitions[0].reason_code is ReasonCode.EVIDENCE_MISSING

def test_alarm_categories_are_set(graph_ab) -> None:
    result = apply(graph_ab, initial_state(graph_ab, "e", T0),
                   make_event("b_done"), T0)
    assert result.alarms[0].category == "PROCESS_COMPLIANCE"
    assert result.alarms[0].severity == "HIGH"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_execution.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `derive_execution_status`, failure matching, alarms**

Failure is checked before completion for a step. A `NEEDS_REVIEW` step is terminal for execution-status purposes. `derive_execution_status` is pure and used by `apply` and by the backend after `timed_out`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_execution.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/app/domain/sop/model.py backend/tests/domain/sop/test_engine_execution.py
git commit -m "feat(domain): derive execution status and emit alarms"
```

---

### Task 14: Optional steps and skip audit

**Files:**
- Modify: `backend/app/domain/sop/engine.py`
- Create: `backend/tests/domain/sop/test_engine_skip.py`

**Interfaces:**
- Behavior:
  - `skip_if.all_steps_completed`: on settle, if all referenced steps are `COMPLETED`/`SKIPPED` → `SKIPPED`.
  - `skip_if.event_type`: a matching event → `SKIPPED`.
  - `StepState.skipped_reason` records `"all_steps_completed:<keys>"` or `"event_type:<type>"`; the skip transition's `detail` carries the same string.
  - Transition reason code `AUTO_SKIP`.
  - Skipped steps unlock downstream exactly like completed steps.
  - Required steps never skip (schema rejects).

**Fixtures used here:** `skip_graph` = `a` (start, `EVENT_RULE all [a_done]`), `optional` (depends `a`, `required=False`, `skip_if.all_steps_completed=["a"]`, `EVENT_RULE all [optional_done]`), `after` (depends `optional`, `EVENT_RULE all [after_done]`); `skip_event_graph` = `optional` (start, `required=False`, `skip_if.event_type="skip_now"`, `EVENT_RULE all [optional_done]`), `after` (depends `optional`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_skip.py

def test_skip_by_completed_steps(skip_graph) -> None:
    result = apply(skip_graph, initial_state(skip_graph, "e", T0),
                   make_event("a_done"), T0 + timedelta(seconds=1))
    skipped = next(t for t in result.step_transitions if t.step_key == "optional")
    assert skipped.to_status is StepStatus.SKIPPED
    assert skipped.reason_code is ReasonCode.AUTO_SKIP

def test_skip_by_event(skip_event_graph) -> None:
    result = apply(skip_event_graph, initial_state(skip_event_graph, "e", T0),
                   make_event("skip_now"), T0)
    skipped = next(t for t in result.step_transitions if t.step_key == "optional")
    assert skipped.to_status is StepStatus.SKIPPED

def test_skip_reason_is_recorded(skip_graph) -> None:
    state = advance(skip_graph, initial_state(skip_graph, "e", T0),
                    [make_event("a_done")])
    assert state.steps["optional"].skipped_reason == "all_steps_completed:a"

def test_skipped_step_unlocks_downstream(skip_graph) -> None:
    result = apply(skip_graph, initial_state(skip_graph, "e", T0),
                   make_event("a_done"), T0 + timedelta(seconds=1))
    assert any(t.step_key == "after" and t.to_status is StepStatus.ACTIVE
               for t in result.step_transitions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_skip.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement skip evaluation in `_settle` and event handling**

Evaluate skips before activation. A step that skips does not activate or start a timeout. Set the skip transition's `detail` to the audit string; `advance` copies it into `skipped_reason`. Add `AUTO_SKIP` to `ReasonCode` if Task 1 did not already include it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_skip.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/tests/domain/sop/test_engine_skip.py
git commit -m "feat(domain): support optional steps with audited skips"
```

---

### Task 15: Joins and `STATE_RULE` re-evaluation

**Files:**
- Modify: `backend/app/domain/sop/engine.py`
- Create: `backend/tests/domain/sop/test_engine_join.py`

**Interfaces:**
- Behavior:
  - A join node activates only when **all** dependencies are terminal (`COMPLETED`/`SKIPPED`/`FAILED`/`TIMED_OUT`/`NEEDS_REVIEW`).
  - `ALL_REQUIRED`: complete only if all deps are `COMPLETED`/`SKIPPED`; otherwise `NEEDS_REVIEW` with `EVIDENCE_MISSING`.
  - `ANY_OF_N`: complete if at least N deps are `COMPLETED`/`SKIPPED`; otherwise `NEEDS_REVIEW`.
  - `STATE_RULE` `all_steps_completed`: all listed steps completed/skipped.
  - `STATE_RULE` `any_steps_completed`: at least one listed step completed/skipped.
  - Re-evaluate after every transition until stable (bounded by step count); never unlock a join before all deps are terminal.
  - A non-join step activates only when **all** dependencies are `COMPLETED`/`SKIPPED`; if a dependency is `FAILED`/`TIMED_OUT`/`NEEDS_REVIEW`, the step stays `PENDING` and the execution derives `NEEDS_REVIEW`.
  - A join node's `completion` exists only to satisfy the schema; the engine judges it by `join_policy`.

**Fixtures used here:** `parallel_join_graph` = `left` (start, `EVENT_RULE all [left_done]`), `right` (start, `EVENT_RULE all [right_done]`), `join` (`CHECKPOINT`, depends `left,right`, `join_policy="ALL_REQUIRED"`, `completion` `STATE_RULE all_steps_completed ["left","right"]`), `check` (`CHECKPOINT`, depends `join`, `completion` `STATE_RULE all_steps_completed ["left","right"]`). `any_join_graph` = `left` (start, `EVENT_RULE all [left_done]`, `failure {event_type:"left_fail", reason_code:"EVIDENCE_MISSING"}`), `right` (start, `EVENT_RULE all [right_done]`, `failure {event_type:"right_fail", reason_code:"EVIDENCE_MISSING"}`), `join` (depends both, `join_policy={"type":"ANY_OF_N","n":1}`, `completion` `STATE_RULE all_steps_completed ["left","right"]`). `state_with_left_done(graph)` = `advance(graph, initial_state(graph, "e", T0), [make_event("left_done")])`; `state_with_left_failed(graph)` = `advance(..., [make_event("left_fail")])`. These two are plain helper functions, not pytest fixtures.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_engine_join.py

def test_join_waits_for_all_dependencies(parallel_join_graph) -> None:
    state = initial_state(parallel_join_graph, "e", T0)
    after_left = apply(parallel_join_graph, state, make_event("left_done"), T0)
    assert all(t.step_key != "join" for t in after_left.step_transitions)

def test_all_required_completes_when_both_done(parallel_join_graph) -> None:
    state = state_with_left_done(parallel_join_graph)
    result = apply(parallel_join_graph, state,
                   make_event("right_done", event_id="e-2"), T0)
    assert any(t.step_key == "join" and t.to_status is StepStatus.COMPLETED
               for t in result.step_transitions)

def test_any_of_n_completes_with_one_success(any_join_graph) -> None:
    state = state_with_left_done(any_join_graph)
    result = apply(any_join_graph, state,
                   make_event("right_fail", event_id="e-2"), T0)
    assert any(t.step_key == "join" and t.to_status is StepStatus.COMPLETED
               for t in result.step_transitions)

def test_any_of_n_not_met_goes_to_review(any_join_graph) -> None:
    state = state_with_left_failed(any_join_graph)
    result = apply(any_join_graph, state,
                   make_event("right_fail", event_id="e-2"), T0)
    assert any(t.step_key == "join" and t.to_status is StepStatus.NEEDS_REVIEW
               for t in result.step_transitions)

def test_state_rule_checkpoint_completes(parallel_join_graph) -> None:
    state = state_with_left_done(parallel_join_graph)
    result = apply(parallel_join_graph, state,
                   make_event("right_done", event_id="e-2"), T0)
    assert any(t.step_key == "check" and t.to_status is StepStatus.COMPLETED
               for t in result.step_transitions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_join.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement join readiness, join completion, and `STATE_RULE`**

`_settle` evaluates in this order per pass: skips → activation (including joins) → `STATE_RULE` completion → join completion. Repeat until no change. Cap at `len(graph.steps) + 1` passes; raise `RuntimeError` if exceeded (defensive, indicates a bug).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_engine_join.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/engine.py backend/tests/domain/sop/test_engine_join.py
git commit -m "feat(domain): add joins and state-rule re-evaluation"
```

---

### Task 16: Multi-camera correlation

**Files:**
- Create: `backend/app/domain/sop/correlation.py`
- Create: `backend/tests/domain/sop/test_correlation.py`

**Interfaces:**
- Produces: `CandidateEvent(event_id, event_type, camera_id, camera_role, confidence, occurred_at, correlation_key, conclusion)`
- Produces: `CorrelationConflict(correlation_key, event_ids, reason_code)`
- Produces: `CorrelationResult(accepted: tuple[CandidateEvent, ...], conflicts: tuple[CorrelationConflict, ...], reason_code: ReasonCode | None)`
- Produces: `correlate(events, *, required_roles=(), min_independent_evidence=1, max_skew_ms=2000, priority=None) -> CorrelationResult`
- Behavior:
  - Dedupe same camera + same `correlation_key` (keep first by `occurred_at`, tie-break `event_id`).
  - Different cameras with the same `correlation_key` are independent evidence; never average confidence.
  - Same `correlation_key`, mutually exclusive `conclusion` within `max_skew_ms` → conflict. With `priority` (role → rank), pick the highest rank; without, `reason_code=CAMERA_CONFLICT`.
  - Missing required role → `EVIDENCE_MISSING`.
  - Fewer than `min_independent_evidence` agreeing events → `EVIDENCE_MISSING`.
  - Events without a `correlation_key` are never deduped across events.

**Test helper (`test_correlation.py`):** `cam(event_id, camera_id, key, *, role="hands", conclusion="installed", occurred_at=T0, confidence=0.9) -> CandidateEvent` fills the remaining fields (`event_type="part_placed"`) and returns a `CandidateEvent`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/domain/sop/test_correlation.py

def test_same_camera_duplicate_is_deduped(cam) -> None:
    result = correlate([cam("e1", "c1", "k1"), cam("e2", "c1", "k1")])
    assert [e.event_id for e in result.accepted] == ["e1"]

def test_different_cameras_are_independent(cam) -> None:
    result = correlate([cam("e1", "c1", "k1"), cam("e2", "c2", "k1")])
    assert len(result.accepted) == 2

def test_conflict_without_priority_needs_review(cam) -> None:
    result = correlate([cam("e1", "c1", "k1", conclusion="installed"),
                        cam("e2", "c2", "k1", conclusion="missing")])
    assert result.reason_code is ReasonCode.CAMERA_CONFLICT
    assert result.conflicts

def test_conflict_with_priority_picks_higher_rank(cam) -> None:
    result = correlate([cam("e1", "c1", "k1", role="hands", conclusion="installed"),
                        cam("e2", "c2", "k1", role="tool", conclusion="missing")],
                       priority={"hands": 2, "tool": 1})
    assert [e.event_id for e in result.accepted] == ["e1"]

def test_missing_required_role_needs_review(cam) -> None:
    result = correlate([cam("e1", "c1", "k1", role="hands")],
                       required_roles={"overview"})
    assert result.reason_code is ReasonCode.EVIDENCE_MISSING

def test_insufficient_independent_evidence_needs_review(cam) -> None:
    result = correlate([cam("e1", "c1", "k1")], min_independent_evidence=2)
    assert result.reason_code is ReasonCode.EVIDENCE_MISSING

def test_no_key_is_not_deduped(cam) -> None:
    result = correlate([cam("e1", "c1", None), cam("e2", "c1", None)])
    assert len(result.accepted) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/domain/sop/test_correlation.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement correlation**

Sort inputs by `(occurred_at, event_id)` for determinism. Group by non-null `correlation_key`. A group is a conflict when it has more than one distinct non-null `conclusion` and the time span is within `max_skew_ms`. Independent evidence counts distinct `camera_id`. Never compute an average confidence.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/domain/sop/test_correlation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/sop/correlation.py backend/tests/domain/sop/test_correlation.py
git commit -m "feat(domain): add rule-driven multi-camera correlation"
```

---

## Final verification

- [ ] **Run all package tests**

```bash
uv run --package contracts pytest contracts/tests -v
uv run --package sop_dsl pytest sop_dsl/tests -v
cd backend && uv run pytest tests -v
```

- [ ] **Run strict type checks**

```bash
cd backend && uv run mypy app && uv run ty check app
cd ../contracts && uv run mypy contracts && uv run ty check contracts
cd ../sop_dsl && uv run mypy sop_dsl && uv run ty check sop_dsl
```

- [ ] **Run lint/format**

```bash
cd backend && uv run ruff check app tests && uv run ruff format --check app tests
cd ../contracts && uv run ruff check contracts tests && uv run ruff format --check contracts tests
cd ../sop_dsl && uv run ruff check sop_dsl tests && uv run ruff format --check sop_dsl tests
```

- [ ] **Run backend coverage and confirm ≥ 90%**

```bash
cd backend && uv run bash scripts/test.sh
```

- [ ] **Verify the Docker image still builds with the workspace members**

```bash
docker compose build backend
```

- [ ] **Verify no API schema drift**

```bash
bash ./scripts/generate-client.sh
git diff --exit-code frontend/openapi.json frontend/src/client
```

- [ ] **Update `.pre-commit-config.yaml` and `backend/scripts/lint.sh` paths**

Change the local `mypy` and `ty` hooks from `backend/app` to `backend/app contracts/contracts sop_dsl/sop_dsl`. In `backend/scripts/lint.sh`, append `../contracts/contracts ../sop_dsl/sop_dsl` to the `mypy`, `ty check`, `ruff check`, and `ruff format` targets.

- [ ] **Commit**

```bash
git add .pre-commit-config.yaml backend/scripts/lint.sh contracts/pyproject.toml sop_dsl/pyproject.toml uv.lock
git commit -m "chore: include the new workspace packages in type checks"
```
