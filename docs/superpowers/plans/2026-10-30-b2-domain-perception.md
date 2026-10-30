# VisiSOP B2 — 领域感知与真实 SOP（遥控器装电池）实施计划

> **执行方式：** REQUIRED SUB-SKILL：使用 `superpowers:subagent-driven-development` 或
> `superpowers:executing-plans`，按任务 checkbox 推进。
>
> **前置：** B1 垂直切片（`2026-10-28-vertical-slice-30-40-50.md`）的管道已跑通。
> 本计划**替换**其“区域约定触发”的检测语义，不保留兼容层。

**目标：** 把检测从“框中心落在人工矩形里”升级为
**感知原语 → 结构化观测 → 属性谓词 → SOP 状态**。以“空调遥控器装电池 SOP”端到端验收：
识别遥控器、电池数量与极性、盖子开合、手是否离开；前端可看到检测框/区域/观测；
事件级 precision/recall 达标，验收场景误完成率为 0。

**非目标：** 端到端学习 SOP、VLM 判定、跨相机几何融合、自动生成 DSL、为单个 SOP 写一次性脚本。

---

## 1. 现状与根因

当前 B1 检测是**区域约定**：

```
YOLO(COCO 80 类) → 框中心 ∈ 人工矩形 → 固定事件类型 → 事件类型匹配即完成
```

它只能证明“事件 → 状态 → 证据 → 审计”的管道，不能表达：

| 真实 SOP 需要 | 当前能力 |
|---|---|
| 电池装了几节 | 无 `count` 属性 |
| 电池极性是否正确 | 无 `orientation` |
| 盖子是否合上 | 无 `state` |
| 手是否已离开 | 无 `hand` 类、无“缺席”事件 |
| 经过区域 vs 完成动作 | 区域存在 = 完成 |

根因不在阈值，而在**观测词汇**与**规则语义**：事件只有“某类物体出现在某区域”，
SOP 条件只有“事件类型 + 置信度 + 稳定时长”。B2 同时修这三层。

## 2. 架构

```
每相机一次共享感知（检测 + 跟踪）
        │  Perception{detections, tracks, frame, at}
        ▼
原语（primitives，纯后处理，可单测）
  object_present / object_absent / count_threshold / state_classify / orientation_match
        │  Observation{primitive, params, attributes, confidence, evidence}
        ▼
EventBuilder（去抖、stable_for_ms、correlation_key、绑定参数、params_hash）
        │  VisionEvent{event_type, attributes, observation_ids, primitive_id/version, model}
        ▼
Backend：属性校验 → resolver → engine（属性谓词 + 状态规则）→ 步骤/执行/告警/审计/outbox
```

**权威边界不变：** PostgreSQL 是唯一状态权威；runtime 只报告观测；前端只渲染后端状态。
**语义位置：** 领域语义在 `contracts/catalog.py`（事件类型 = 原语实例）与 SOP DSL；
矩形/ROI/阈值只是原语参数，不再承载“步骤完成”。

## 3. 技术栈

- 现有：Python 3.14 backend / 3.12 runtime、FastAPI、SQLModel、PostgreSQL、ONNX Runtime、OpenCV。
- 新增（仅训练/导出工具，**不进 runtime 运行时依赖**）：`ultralytics`（YOLO11n-seg/det 微调）。
- 跟踪：先实现轻量 IoU tracker（无新依赖）；ByteTrack 作为后续可替换实现。
- 数据：现场录制的图像/短视频 + 标注；数据与模型制品**不入 git**。

## 4. 规格与依据

- `docs/AI_SOP_Perception_Primitive_Catalog_v0.1.md`（本计划的设计基线）
- `docs/AI_SOP_Platform_Architecture_v2.0.md` §7.5、§8、§12
- `docs/implementation/{10,20,30,40,50,70}-*.md`
- `docs/design/*`、`AGENTS.md`

## 5. 全局约束

- **开发期不保留兼容。** DSL 升到 `schema_version: "2.0"`，1.x 直接拒绝；旧的
  `ZoneMapper`/zone-only 配置路径删除；bottle 演示改写成 `object_in_zone` 原语实例。
  不写迁移脚本，不维护双路径。
- **相机**：只写曝光/增益；分辨率、像素格式、触发、包大小沿用 MVS。帧按实际
  `enPixelType` 解码。
- **时间**：UTC-aware；域名函数收 `now`，不调用 `datetime.now()`。
- **词汇**：状态、原因码、角色、处理结果只来自 `contracts.enums` / `domain.sop.model`。
- **置信度**：原语输出必须声明 `calibrated | deterministic | uncalibrated`；未校准
  原语只能走 `NEEDS_REVIEW` 或保守阈值（catalog §5）。
- **证据**：仍是 keyframe 进 `EVIDENCE_DIR/tmp` → 后端校验/移动；预览不是证据。
- **客户端**：只用生成客户端；不改 `routeTree.gen.ts`。
- **门禁**：`ruff`、严格 `mypy`/`ty`、后端覆盖率 ≥90%、`bun run lint/build`、
  Playwright、runtime `ruff` + `pytest`；路由/模型变更后重新生成客户端。
- **提交**：每个任务一个 conventional commit；不留未提交的工作区。

## 6. 本计划确定的 ADR

- **ADR-0004 — 采用感知原语目录；事件类型 = 原语实例。**
  事件类型由 `contracts/catalog.py` 注册并随包版本发布；工位只绑定参数。
  原语只做单相机视觉，不感知 SOP/步骤；引擎只认事件。
  何时改变：出现必须端到端学习的动作，或原语目录条目爆炸到无法维护。
- **ADR-0005 — DSL v2 属性谓词。**
  `EventCondition.attributes: dict[str, AttributePredicate]`，谓词为 `eq | in | gte | lte | exists`；
  计数、状态、极性不再靠“每个取值一个新事件类型”。1.x 不兼容。
  何时改变：需要跨事件属性聚合/表达式时再评估（不在 B2）。
- **ADR-0006 — B2.0 绑定与观测的落点。**
  绑定先放 runtime YAML（`bindings[]`），事件携带 `binding_id` 与 `params_hash`；
  `Observation` 不单独入库，事件携带决定性属性 + `observation_ids` + keyframe；
  `perception_bindings` 表与 config bundle API 延后到多工位阶段。
  何时改变：第二个工位/相机上线，或需要运行时改参数。

## 7. 文件地图

```
contracts/contracts/primitives.py                  # 原语注册、Observation、置信度语义
contracts/contracts/catalog.py                     # 事件类型 = 原语实例 + 属性 schema（重写）
contracts/tests/test_primitives.py
contracts/tests/test_catalog.py                    # 属性 schema、关联键

sop_dsl/sop_dsl/schema.py                          # DSL v2：属性谓词
sop_dsl/sop_dsl/validate.py                        # 谓词键/类型校验
sop_dsl/tests/test_schema.py

backend/app/domain/sop/model.py                    # MatchedEvent 增加 attributes
backend/app/domain/sop/engine.py                   # 属性谓词匹配
backend/app/application/state_codec.py             # attributes 编解码
backend/app/application/event_service.py           # 属性透传/校验
backend/tests/domain/sop/test_engine_attributes.py
backend/tests/application/test_ingestion.py

runtime/video_runtime/perception.py                # Perception、IoU tracker、共享检测
runtime/video_runtime/primitives/{__init__,base,presence,count,state,orientation,absence}.py
runtime/video_runtime/event_builder.py             # 由原语观测构建事件（替换 zone 逻辑）
runtime/video_runtime/zones.py                     # 删除或降为 object_in_zone 的参数解析
runtime/video_runtime/config.py                    # bindings[] 替换 zones[]
runtime/video_runtime/state.py                     # 预览叠加检测框/区域/标签
runtime/video_runtime/server.py                    # GET /detections/{camera_id}
runtime/tests/{test_primitives,test_event_builder,test_overlay,test_tracker}.py
runtime/tools/record_clips.py                      # 现场素材采集
runtime/eval/event_eval.py                         # 事件级 precision/recall/误完成率

backend/app/seed/remote_battery.json               # 第一个真实 SOP
backend/app/seed/bottle_transfer.json              # 迁移到 DSL v2 + 原语事件
runtime/config.demo.yaml                           # bindings + 新模型
docs/runbooks/{b2-acceptance,camera-spike}.md
docs/adr/0004-*.md, 0005-*.md, 0006-*.md
```

**删除（不兼容）：** `runtime/video_runtime/zones.py` 的 `ZoneMapper` 语义、
`EventBuilder` 的 zone 分支、`config.zones`、DSL v1 的 `SCHEMA_VERSION` 支持。

---

## Phase 0 — 契约、DSL v2、引擎谓词

### Task 1: 原语与事件目录（遥控器装电池 + bottle 迁移）

**Files:**
- Create: `contracts/contracts/primitives.py`
- Rewrite: `contracts/contracts/catalog.py`
- Test: `contracts/tests/test_primitives.py`, `contracts/tests/test_catalog.py`

**Interfaces:**
- `PrimitiveSpec(primitive_id, version, params_model, description)`
- `register_primitive(spec)`; `get_primitive(id)`; `primitive_snapshot()`
- `EventTypeSpec` 扩展：`primitive_id: str`, `params_schema: type[BaseModel]`,
  `confidence_semantics: Literal["calibrated","deterministic","uncalibrated"]`,
  `evidence_kind: Literal["keyframe","clip","none"]`
- 事件类型（属性模型 `extra="forbid"`）：
  - `remote_present`：`zone: str`
  - `batteries_installed`：`compartment: str, count: int, slots: int`
  - `battery_orientation_ok`：`compartment: str, orientation: Literal["CORRECT","REVERSED"]`
  - `remote_lid_closed`：`state: Literal["OPEN","CLOSED"]`
  - `operator_hand_clear`：`zone: str, present: bool`
  - `bottle_in_pickup_zone` / `bottle_in_target_zone`：`object_class, zone, bbox`
    （改为 `object_in_zone` 原语实例，名字不变，事件语义不变）

- [ ] **Step 1: 写失败测试**

```python
# contracts/tests/test_catalog.py
def test_battery_events_are_primitive_instances() -> None:
    spec = get_event_type("batteries_installed")
    assert spec.primitive_id == "count_threshold"
    attr = validate_attributes(
        "batteries_installed",
        {"compartment": "remote", "count": 2, "slots": 2},
    )
    assert attr.model_dump()["count"] == 2

def test_attributes_are_strict() -> None:
    with pytest.raises(InvalidAttributes):
        validate_attributes(
            "batteries_installed",
            {"compartment": "remote", "count": 2, "slots": 2, "extra": 1},
        )
```

- [ ] **Step 2: 运行确认失败**

`uv run --package contracts pytest contracts/tests/test_catalog.py -q`

- [ ] **Step 3: 实现**

1. `primitives.py` 注册 v0 原语：`object_present`, `object_absent`,
   `object_in_zone`, `count_threshold`, `state_classify`, `orientation_match`。
2. `catalog.py` 的每个事件类型指向一个原语；`confidence_semantics` 明确；
   `correlation_key_template` 只用允许的占位符。
3. bottle 事件保留名字，改挂 `object_in_zone`；属性模型与 demo 一致。
4. 删除不再使用的事件类型（`frame_placed` 等保留给测试/示例的，若无引用一并删除）。

- [ ] **Step 4: 跑测试**

`uv run --package contracts pytest contracts/tests -q`

- [ ] **Step 5: 提交**

```bash
git add contracts
git commit -m "feat(contracts): register perception primitives and battery SOP events"
```

---

### Task 2: DSL v2 属性谓词

**Files:**
- Modify: `sop_dsl/sop_dsl/schema.py`, `validate.py`
- Test: `sop_dsl/tests/test_schema.py`, `test_validate.py`

**Interfaces:**

```python
class AttributePredicate(_StrictModel):
    eq: Any | None = None
    in_: tuple[Any, ...] | None = Field(default=None, alias="in")
    gte: float | int | None = None
    lte: float | int | None = None
    exists: bool | None = None

class EventCondition(_StrictModel):
    event_type: str
    min_confidence: float = 0.0
    stable_for_ms: int = 0
    within_ms: int | None = None
    source_camera_role: str | None = None
    attributes: dict[str, AttributePredicate] = {}
```

`SCHEMA_VERSION = "2.0"`；`SUPPORTED_SCHEMA_VERSIONS = {"2.0"}`。

- [ ] **Step 1: 写失败测试**

```python
def test_count_and_state_predicates_parse() -> None:
    spec = SOPSpec.model_validate({
        "schema_version": "2.0", "sop_key": "remote_battery", "version": 1,
        "name": "遥控器装电池",
        "steps": [{
            "key": "insert_batteries", "name": "装入两节电池", "type": "ACTION",
            "completion": {"mode": "EVENT_RULE", "all": [{
                "event_type": "batteries_installed",
                "attributes": {"count": {"gte": 2}, "slots": {"eq": 2}},
            }]},
        }],
    })
    cond = spec.steps[0].completion.all[0]
    assert cond.attributes["count"].gte == 2

def test_schema_v1_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SOPSpec.model_validate({... "schema_version": "1.0" ...})
```

- [ ] **Step 2: 运行确认失败**

`uv run --package sop_dsl pytest sop_dsl/tests -q`

- [ ] **Step 3: 实现**

1. 加 `AttributePredicate` 与 `EventCondition.attributes`；`not` 分支复用同一类型。
2. `validate.py`：谓词键必须存在于该事件类型的属性模型；`gte/lte` 只允许数值；
   `eq/in` 类型与属性类型兼容；未知事件类型报 `UNKNOWN_EVENT_TYPE`。
3. 删除/拒绝 v1；bottle SOP JSON 同步改成 2.0。

- [ ] **Step 4: 跑测试**

`uv run --package sop_dsl pytest sop_dsl/tests -q`

- [ ] **Step 5: 提交**

```bash
git add sop_dsl backend/app/seed/bottle_transfer.json
git commit -m "feat(dsl): replace event-only conditions with attribute predicates"
```

---

### Task 3: 引擎属性匹配与证据记录

**Files:**
- Modify: `backend/app/domain/sop/model.py`（`MatchedEvent.attributes`）
- Modify: `backend/app/domain/sop/engine.py`
- Modify: `backend/app/application/state_codec.py`, `execution_service.py`
- Test: `backend/tests/domain/sop/test_engine_attributes.py`

**Interfaces:**
- `MatchedEvent.attributes: Mapping[str, Any] = field(default_factory=dict)`
- 引擎 `_single_event_matches` 先校验属性谓词，再判置信度/时间窗；
- `matched_to_json`/`matched_from_json` 保留 attributes；
- `ExecutionDetailRead` 的 matched events 带 attributes（供审计/前端）。

- [ ] **Step 1: 写失败测试**

```python
def test_count_predicate_requires_two_batteries(...) -> None:
    state = start_with_active_step("insert_batteries")
    one = make_event("batteries_installed", {"compartment": "remote", "count": 1, "slots": 2})
    result = apply(graph, state, one, T)
    assert not result.step_transitions

    two = make_event("batteries_installed", {"compartment": "remote", "count": 2, "slots": 2})
    result = apply(graph, state, two, T + timedelta(milliseconds=600))
    assert result.step_transitions[0].to_status is StepStatus.COMPLETED
```

- [ ] **Step 2: 运行确认失败**

`cd backend && uv run pytest tests/domain/sop/test_engine_attributes.py -q`

- [ ] **Step 3: 实现**

1. `_matched_event` 从 `VisionEvent.attributes` 复制到 `MatchedEvent.attributes`。
2. `_single_event_matches`：先匹配事件类型/相机角色，再逐条检查属性谓词
   （`eq/in/gte/lte/exists`），最后才是置信度与 `within_ms`。
3. `state_codec` 往返保留 attributes；旧 JSON 无该字段时按空表处理（仅 JSON 解码
   的健壮性，不是 DSL 兼容）。
4. `get_execution` 输出 attributes。

- [ ] **Step 4: 跑测试**

`cd backend && uv run pytest tests/domain/sop tests/application/test_ingestion.py -q`

- [ ] **Step 5: 提交**

```bash
git add backend
git commit -m "feat(engine): match completion conditions on event attributes"
```

---

## Phase 1 — Runtime 原语框架与可见性

### Task 4: 共享感知、跟踪、原语

**Files:**
- Create: `runtime/video_runtime/perception.py`
- Create: `runtime/video_runtime/primitives/{__init__,base,presence,count,state,orientation,absence}.py`
- Rewrite: `runtime/video_runtime/event_builder.py`, `config.py`（`bindings[]`）
- Delete: `runtime/video_runtime/zones.py`（原语参数内联到 binding）
- Test: `runtime/tests/test_tracker.py`, `test_primitives.py`, `test_event_builder.py`

**Interfaces:**
- `Perception(detections, tracks, frame, at)`；`Track(track_id, class_name, bbox, confidence, hits, last_seen)`
- `IoUTracker.update(detections, at) -> list[Track]`（IoU + 类别 + 最大丢失帧）
- `Primitive` Protocol：`evaluate(perception, binding) -> list[Observation]`
- `Observation(primitive_id, primitive_version, attributes, confidence, evidence_frame)`
- 原语：
  - `object_present`：`{zone, object_class, min_conf}` → `{zone}`
  - `object_absent`：连续 N 帧未命中 → `{zone, present: false}`
  - `count_threshold`：ROI 内实例计数 → `{compartment, count, slots}`
  - `state_classify`：ROI + 状态类模型 → `{state}`
  - `orientation_match`：关键点/几何 → `{orientation}`
- `Binding(event_type, primitive_id, params, evidence: bool)`；config `bindings[]`
- `EventBuilder.build(frame, perception, now)`：原语 → 观测 → 去抖/`stable_for_ms` →
  `VisionEvent(attributes, observation_ids, primitive_id, primitive_version, params_hash)`

- [ ] **Step 1: 写失败测试**

```python
def test_count_primitive_reports_two_batteries() -> None:
    perception = perception_with([
        detection("battery", 0.9, (0.2, 0.3, 0.3, 0.5)),
        detection("battery", 0.9, (0.4, 0.3, 0.5, 0.5)),
    ])
    binding = Binding("batteries_installed", "count_threshold",
                      {"compartment": "remote", "roi": (0.1, 0.2, 0.6, 0.6), "slots": 2})
    [obs] = CountThreshold().evaluate(perception, binding)
    assert obs.attributes == {"compartment": "remote", "count": 2, "slots": 2}

def test_absent_primitive_needs_debounce() -> None:
    primitive = AbsentPrimitive(frames=3)
    assert primitive.evaluate(perception_with([]), binding) == []
    assert primitive.evaluate(perception_with([]), binding) == []
    [obs] = primitive.evaluate(perception_with([]), binding)
    assert obs.attributes["present"] is False
```

- [ ] **Step 2: 运行确认失败**

`cd runtime && uv run pytest tests/test_primitives.py tests/test_tracker.py -q`

- [ ] **Step 3: 实现**

1. 每相机一个共享 `Perception`：检测一次，原语只做后处理；GPU/CPU 预算随相机数增长。
2. IoU tracker：类别内匹配，IoU ≥0.3，丢失 >15 帧删除；track_id 进观测。
3. 原语内部只做帧级平滑；去抖/稳定时长在 EventBuilder；步骤完成在引擎。
4. `params_hash = sha256(canonical json(binding params))`；事件带 `binding_id`。
5. bottle demo 用 `object_in_zone` 原语重新配置，事件名/语义不变。

- [ ] **Step 4: 跑测试**

`cd runtime && uv run pytest tests -q && uv run ruff check .`

- [ ] **Step 5: 提交**

```bash
git add runtime
git commit -m "feat(runtime): replace zone triggers with shared perception primitives"
```

---

### Task 5: 预览叠加与检测接口

**Files:**
- Modify: `runtime/video_runtime/state.py`, `server.py`, `config.py`
- Test: `runtime/tests/test_overlay.py`, `test_server.py`

**Interfaces:**
- `RuntimeState.set_perception(camera_id, perception)`；预览 JPEG 在编码前叠加：
  检测框、类别/置信度、track_id、原语区域、当前观测标签；
- 配置 `preview.overlay: "off" | "boxes" | "all"`（默认 `all`）；
- `GET /detections/{camera_id}` → `{at, detections:[...], tracks:[...], observations:[...]}`；
- 叠加不影响证据帧：证据仍用未叠加或仅框注的帧？**决定**：证据帧画检测框与区域，
  不画原语标签（可审计、不遮挡）。

- [ ] **Step 1: 写失败测试**

```python
def test_overlay_draws_boxes() -> None:
    state = RuntimeState(runtime_id="runtime-01", overlay="boxes")
    state.set_perception("cam-01", perception_with([detection("bottle", 0.9, (0.1, 0.1, 0.5, 0.5))]))
    jpeg = state.jpeg("cam-01")
    assert jpeg is not None and jpeg[:2] == b"\xff\xd8"

def test_detections_endpoint_lists_tracks() -> None:
    client = TestClient(create_app(state))
    body = client.get("/detections/cam-01").json()
    assert body["tracks"][0]["class_name"] == "bottle"
```

- [ ] **Step 2: 运行确认失败 / Step 3: 实现**

`cv2.rectangle` + `cv2.putText`；坐标用归一化 × 帧尺寸；空感知返回空列表，不 500。

- [ ] **Step 4: 跑测试 / Step 5: 提交**

```bash
git add runtime
git commit -m "feat(runtime): overlay detections and expose a detections endpoint"
```

---

## Phase 2 — 遥控器装电池：数据、模型、端到端

### Task 6: 数据集与采集工具

**Files:**
- Create: `runtime/tools/record_clips.py`（按 `--seconds/--fps` 录片段 + 帧）
- Create: `runtime/eval/README.md`（目录、标注格式、版本）
- 数据目录（gitignore）：`runtime/data/remote-battery/{raw,frames,labels}/`

**标注类：** `remote`, `battery`, `lid`（或 `lid_open`/`lid_closed` 作为分类标签），
`hand`；标注格式 YOLO txt（检测）+ 整帧分类标签（盖子状态/极性）。

- [ ] **Step 1: 采集 30 次独立录制**（3 名操作者 × 10 遍，含正常/少装/装反/未合盖/手挡）
- [ ] **Step 2: 标注与抽检**（每类 ≥200 实例；抽 10% 复核）
- [ ] **Step 3: 提交工具与清单**（数据本身不入 git）

```bash
git add runtime/tools/record_clips.py runtime/eval/README.md .gitignore
git commit -m "feat(runtime): add a recording tool and the dataset layout"
```

### Task 7: 模型训练、导出与事件级评测

**Files:**
- Create: `runtime/eval/event_eval.py`
- Create: `runtime/models/remote_battery.yaml`（模型名/版本/类名/校准版本）
- 模型制品（gitignore）：`runtime/models/remote_battery.onnx`

**训练：** YOLO11n 微调（检测；盖子/极性用 ROI 分类头或几何规则），导出 opset 17、
`imgsz=640`、不烘 NMS；类名写入 `models/remote_battery.names`。

**评测（catalog §7）：** 回放黄金视频 → 原语 → 事件，按事件级匹配：
precision ≥0.99、recall ≥0.95、latency p95 ≤500 ms、误完成率 0（≥30 次录制）。
未达标不得进入 Task 9。

- [ ] **Step 1: 实现回放/匹配器**（时间窗 1000 ms、属性相等、一对一贪心）
- [ ] **Step 2: 训练并导出**，记录 mAP、事件级指标、校准版本
- [ ] **Step 3: 提交评测器与模型清单**（ONNX 不入 git）

```bash
git add runtime/eval runtime/models/remote_battery.yaml .gitignore
git commit -m "feat(runtime): add event-level evaluation and the battery model manifest"
```

### Task 8: 装电池 SOP、事件绑定与回放验收

**Files:**
- Create: `backend/app/seed/remote_battery.json`
- Modify: `runtime/config.demo.yaml`（`bindings[]`：5 类事件 + ROI/阈值）
- Modify: `backend/app/scripts/seed_demo.py`（可选：seed 第二个 SOP/工位，或参数化）
- Test: `runtime/tests/test_remote_battery_sop.py`（回放黄金视频片段）

**SOP（DSL v2）：**

```json
{
  "schema_version": "2.0",
  "sop_key": "remote_battery",
  "version": 1,
  "name": "遥控器装电池",
  "steps": [
    {"key": "place_remote", "name": "放置遥控器", "type": "ACTION", "timeout_ms": 300000,
     "completion": {"mode": "EVENT_RULE", "all": [
       {"event_type": "remote_present", "min_confidence": 0.9, "stable_for_ms": 500,
        "attributes": {"zone": {"eq": "battery_bench"}}}]},
     "evidence": {"required": true, "kind": "keyframe"}},
    {"key": "insert_batteries", "name": "装入两节电池", "type": "ACTION",
     "depends_on": ["place_remote"], "timeout_ms": 300000,
     "completion": {"mode": "EVENT_RULE", "all": [
       {"event_type": "batteries_installed", "min_confidence": 0.9, "stable_for_ms": 500,
        "attributes": {"count": {"gte": 2}, "slots": {"eq": 2}}},
       {"event_type": "battery_orientation_ok", "min_confidence": 0.9, "stable_for_ms": 500,
        "attributes": {"orientation": {"eq": "CORRECT"}}}]},
     "evidence": {"required": true, "kind": "keyframe"}},
    {"key": "close_lid", "name": "合上盖子并移开手", "type": "ACTION",
     "depends_on": ["insert_batteries"], "timeout_ms": 300000,
     "completion": {"mode": "EVENT_RULE", "all": [
       {"event_type": "remote_lid_closed", "min_confidence": 0.9, "stable_for_ms": 500,
        "attributes": {"state": {"eq": "CLOSED"}}},
       {"event_type": "operator_hand_clear", "min_confidence": 0.9, "stable_for_ms": 800,
        "attributes": {"present": {"eq": false}}}]},
     "evidence": {"required": true, "kind": "keyframe"}},
    {"key": "verify", "name": "确认完成", "type": "CHECKPOINT",
     "depends_on": ["close_lid"], "timeout_ms": 5000,
     "completion": {"mode": "STATE_RULE", "all_steps_completed": ["close_lid"]}}
  ]
}
```

- [ ] **Step 1: 回放测试**：Three clips（正常、少装、未合盖）→ 断言正常完整、
  异常分别停在对应步骤/超时/复核。
- [ ] **Step 2: 端到端 HTTP 测试**：回放事件 POST `/api/events`，断言步骤/证据/告警。
- [ ] **Step 3: 提交**

```bash
git add backend runtime
git commit -m "feat(demo): add the remote-battery SOP with primitive-backed events"
```

---

## Phase 3 — 后端与前端

### Task 9: 属性事件的入站、复核与展示

**Files:**
- Modify: `backend/app/application/event_service.py`（属性随事件落库/匹配）
- Modify: `backend/app/api/schemas/execution.py`（MatchedEventRead.attributes）
- Test: `backend/tests/api/routes/test_events.py`, `test_executions.py`

- [ ] **Step 1: 写失败测试**：POST 带 attributes 的事件 → 步骤按谓词完成；
  属性非法 → `REJECTED`；复核详情能看到决定性属性。
- [ ] **Step 2-4: 实现并跑测试**
- [ ] **Step 5: 重新生成客户端 + 提交**

```bash
bash ./scripts/generate-client.sh
git add backend frontend/src/client frontend/openapi.json
git commit -m "feat(backend): expose decisive event attributes in execution detail"
```

### Task 10: 前端叠加与观测展示

**Files:**
- Modify: `frontend/src/features/wall/PreviewPanel.tsx`（叠加开关/说明）
- Modify: `frontend/src/features/execution/ExecutionFacts.tsx`, `Timeline.tsx`
- Test: `frontend/tests/{wall,execution}.spec.ts`

- [ ] **Step 1: 写失败测试**：执行详情显示 `电池数量 2/2`、`盖子 CLOSED`、
  `手已离开`；预览标注“检测叠加来自 runtime”。
- [ ] **Step 2-4: 实现并跑测试**
- [ ] **Step 5: 提交**

```bash
git add frontend
git commit -m "feat(frontend): show detection overlay and decisive observations"
```

---

## Phase 4 — 验收

### Task 11: 实验室矩阵、指标与门禁

**Files:**
- Create: `docs/runbooks/acceptance-b2.md`
- Modify: `docs/runbooks/windows-demo.md`, `runtime/README.md`

- [ ] **Step 1: 执行矩阵**：3 操作者 × 10 遍 × {正常、少装、装反、未合盖、手挡}；
  记录事件级 precision/recall、latency、误完成次数。
- [ ] **Step 2: 跑完整门禁**

```bash
cd backend && uv run ruff check app && uv run ruff format app --check && uv run mypy app && uv run ty check app && uv run bash scripts/test.sh
cd ../frontend && bun run lint && bun run build && bunx playwright test
cd ../runtime && uv run ruff check . && uv run pytest -q
cd .. && bash ./scripts/generate-client.sh && git diff --exit-code frontend/src/client frontend/openapi.json
```

- [ ] **Step 3: `/code-review` 分支评审，修复 findings**
- [ ] **Step 4: 提交验收报告与指标**

```bash
git add docs/runbooks docs/adr runtime/README.md
git commit -m "docs: record the B2 perception acceptance results"
```

---

## 验收标准（必须全部满足）

| 指标 | 门槛 | 来源 |
|---|---|---|
| 完成类事件 precision | ≥ 0.99 | catalog §7 |
| 完成类事件 recall | ≥ 0.95 | catalog §7 |
| 端到端延迟 p95 | ≤ 500 ms | catalog §7 |
| 误完成率 | 0（≥30 次录制） | catalog §7 |
| 辅助类事件 precision / recall | ≥ 0.95 / ≥ 0.90 | catalog §7 |
| 漏装/少装/装反/未合盖/手挡 | 全部进入 `NEEDS_REVIEW` 或超时，绝不 `COMPLETED` | 本计划 |
| 前端可见 | 预览有检测框/区域；执行详情有决定性属性 | 本计划 |

## 不在本阶段

- `perception_bindings` 表与 config bundle API（ADR-0006：第二工位再上）。
- `SignalEvent` / PLC / 扫码 / 人工确认源。
- 跨相机几何融合、多相机同一动作。
- VLM 判定、端到端 SOP 学习、自动生成 DSL。
- 模型注册表与历史视频重跑（审计回放只依赖事件日志 + SOP/规则版本）。
- `Observation` 长期存储。

## 风险与回退

- **模型不达标**：保留 B1 区域触发作为演示回退？**不**——按“不做兼容”原则，B2 未达标
  就不替换主路径，B1 分支保留在 git 历史；不维护双路径。
- **相机/机位变化**：重录黄金视频、重跑评测；区域/ROI 只是参数，不触发架构变更。
- **标注成本**：先做 5 类（remote/battery/lid_open/lid_closed/hand），极性先靠几何规则；
  指标不达标再扩类。

## Self-Review

- 覆盖 catalog v0.1 的阶段 2 落点：原语（native）、事件目录、EventBuilder、黄金视频/评测；
  未做绑定表与跨相机，理由写在 ADR-0006。
- 类型一致性：`Observation.attributes` 与 `EventCondition.attributes` 的键来自同一属性模型；
  `MatchedEvent.attributes` 贯穿引擎/API/前端。
- 误完成优先：所有异常场景必须停在 `NEEDS_REVIEW`/超时，验收以 0 误完成为硬门槛。
- 不兼容：DSL v2、删除 ZoneMapper、bottle demo 迁移，无迁移脚本与双路径。
