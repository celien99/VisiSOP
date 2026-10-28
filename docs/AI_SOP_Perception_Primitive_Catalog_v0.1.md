# AI-SOP 感知原语目录设计 v0.1

- **状态**：草案（待评审，评审通过后补 ADR-0002）
- **日期**：2026-10-28
- **定位**：补充 `AI_SOP_Platform_Architecture_v2.0.md` §7.5、§12、§18，回答“任意 SOP 如何配置/训练后检测”
- **不改变**：§6 状态机、§7 事件契约字段、§8 多相机关联规则；冲突时以基线为准

## 0. 一句话结论

**SOP 编排是通用的，检测不是。** 平台的通用性来自有限、可组合、可独立评估的**感知原语**；新 SOP 的成本应该主要花在配置上，而不是每个 SOP 重新训练一个模型。

## 1. 问题与定位

目标不是“某个工序的检测器”，而是“任意标准操作流程都能录入、配置/训练、检测”的平台。把“任意”拆成两层：

| 层 | 是否通用 | 复用单位 | 新需求成本 |
|---|---|---|---|
| SOP 编排（DSL、DAG、状态机） | 是 | 引擎 | 写一份 DSL，分钟级 |
| 检测（视频 → 语义事件） | **否** | 感知原语 | 配置、小样本标注，或训练 |

如果按“一个 SOP 一个端到端模型”做，会同时输掉三件事：

1. **审计**：端到端模型给不出 `reason_code`、规则版本、证据链，而这是系统对工厂的核心承诺；
2. **成本**：每个 SOP 都要采长视频、标注、训练，成本随 SOP 数量线性增长；
3. **泛化**：换光照、机位、产品就要重标，客户项目永远无法沉淀成产品。

规则编排 + 可解释原语，正好是审计闭环需要的形状。

## 2. 概念模型

```
SOP Step (DSL)                     ── 步骤
    │ completion / failure 引用
Event Type (contracts/catalog)     ── 事件类型 = 原语 + 参数（注册项）
    │ 由哪个原语实例化
Primitive (runtime/primitives)     ── 感知原语（代码，可复用）
    │ 输入帧/时间窗 + 参数
Observation → Event                ── 运行时观测到事件的构建
```

| 概念 | 定义 | 属于 | 谁改 |
|---|---|---|---|
| 感知原语 Primitive | 有明确输入输出契约的检测能力；内部可含模型、跟踪、平滑 | `runtime/` | 视觉工程 |
| 事件类型 Event Type | 业务语义事件，是某个原语的参数化实例；在 contracts 注册 | `contracts/catalog/` | 平台/SOP 作者 |
| 事件实例 Event | 运行时产出的一条 `VisionEvent`，带属性与证据 | `vision_events` | 运行时 |
| 工位绑定 Station Binding | 某相机上原语的 ROI、阈值等现场参数 | 配置/数据库 | 现场实施 |

**硬规则**

- 原语只做单相机；跨相机关联永远留在 §8 的 correlation/resolver，不进原语。
- 原语不感知 SOP、步骤、执行实例；它只回答“画面里发生了什么”。
- 引擎只认事件，不认原语；换原语实现不需要动引擎和 DSL。

## 3. 事件类型 = 原语实例（核心设计）

事件类型**不是**每个 SOP 手写的新名字，而是“原语 + 参数”的注册项。

```yaml
# contracts/catalog/left_bolt_installed.yaml
event_type: left_bolt_installed
schema_version: "1.0"
primitive: object_placed
primitive_version: "1.0"
params:
  object_class: bolt
  zone: "{station.left_bolt_zone}"   # 现场绑定后填充
  stable_ms: 500
attributes_schema:
  side: { enum: [left, right] }
  bolt_index: { type: integer, minimum: 0 }
correlation_key: "{workpiece_id}:bolt:{side}"
evidence:
  kind: keyframe
  required: true
```

```yaml
# 同原语、不同参数 → 另一个事件类型，不新增原语
event_type: right_bolt_installed
primitive: object_placed
params: { object_class: bolt, zone: "{station.right_bolt_zone}", stable_ms: 500 }
```

好处：

- 引擎和 DSL v1 **完全不用改**（`completion` 仍然只引用 `event_type` 和阈值）；
- 平台可以度量**原语复用率**（事件类型数 / 原语数）。低于 2 的原语大概率抽象错了；
- 新增 SOP 时优先在目录里找现成事件类型，找不到再组合参数，最后才考虑新原语。

**命名规则**

- 事件名描述业务事实（`left_bolt_installed`），不描述算法（`yolo_bolt_score`）；
- 一个事件类型只映射一个原语，一对多会让审计对不上来源；
- 事件类型只追加、不修改语义；破坏性变更升 `schema_version`（沿用 A28）。

**已知限制**：DSL v1 的 `completion` 只支持 `event_type`、`min_confidence`、`stable_for_ms`、`within_ms`、`source_camera_role`，没有属性谓词。因此每个被 SOP 引用的“原语 + 参数”组合都需要一个目录条目。目录规模靠复用控制，不靠泛化语法。若后期条目爆炸，再评估 DSL v2 的属性谓词（需 ADR）。

## 4. 原语目录 v0

成本等级：

| 等级 | 含义 | 工作量 |
|---|---|---|
| C0 | 配置型：预训练模型/经典 CV，只调参数 | 分钟–小时 |
| C1 | 小样本：新对象类/新状态，少量标注后微调或模板匹配 | 小时–天 |
| C2 | 训练型：新动作/时序类，每个类需要标注视频 | 天–周 |
| C3 | 外部：PLC/传感器/人工，不经过视觉 | 接入即可 |

### A. 存在与状态

| 原语 | 关键参数 | 输出属性 | 实现 | 成本 |
|---|---|---|---|---|
| `object_present` | object_class, roi, min_conf | bbox, confidence | 检测器/模板匹配 | C0–C1 |
| `object_absent` | 同上 | — | 同上的反相 + 去抖 | C0–C1 |
| `count_threshold` | object_class, roi, n, op | count | 检测 + 计数 | C0–C1 |
| `state_classify` | roi, state_set（封闭枚举）, model | state | 分类器/模板 | C1–C2 |

### B. 空间与摆放

| 原语 | 关键参数 | 输出属性 | 实现 | 成本 |
|---|---|---|---|---|
| `object_in_zone` | object, zone, dwell_ms | enter/exit, dwell | 检测 + 多边形 | C0–C1 |
| `object_placed` | object, target_zone, stable_ms | placed, offset | 检测 + 稳定判定 | C1–C2 |
| `relative_position` | object_a, object_b, relation, tolerance | relation_holds | 检测 + 几何 | C1 |
| `orientation_match` | object, ref_orientation, tolerance | angle, match | 关键点/姿态 | C1–C2 |

### C. 人体与动作

| 原语 | 关键参数 | 输出属性 | 实现 | 成本 |
|---|---|---|---|---|
| `person_present` | role/zone | present, track_id | 检测/跟踪 | C0–C1 |
| `hand_in_zone` | zone, hand, dwell_ms | hand, dwell | 姿态/检测 | C1 |
| `pose_action` | action_class（reach/pick/place/press/turn）, zone | action, confidence | 骨架/时序分类 | C1–C2 |
| `two_hand_action` | zone_a, zone_b, sync_ms | both_hands | 姿态 + 同步 | C2 |

### D. 工具与操作

| 原语 | 关键参数 | 输出属性 | 实现 | 成本 |
|---|---|---|---|---|
| `tool_in_use` | tool_class, zone | tool, confidence | 检测 + 区域 | C0–C1 |
| `fastening_action` | tool, zone, min_duration/rotation | fastened, duration | 工具检测 + 动作时序 | C2 |
| `insertion_action` | part, target, depth/dwell | inserted | 相对位置 + 稳定 | C2 |

### E. 检查与外部

| 原语 | 关键参数 | 输出属性 | 实现 | 成本 |
|---|---|---|---|---|
| `surface_inspection` | roi, defect_classes | defect, score | 分类/分割 | C2 |
| `external_signal` | source（PLC/sensor/API）, signal_key | value | 适配器 | C3 |
| `manual_confirm` | prompt, role | confirmed_by | 人工事件源 | C3 |

> v0 的目标不是覆盖所有工序，而是把每类的**契约**定下来。具体先实现哪几个由实验室验证决定（见 §9）。

## 5. 原语输出契约

原语产出 `Observation`，由 EventBuilder 汇总为 `VisionEvent`（沿用 §7.2 字段）。补充：

| 字段 | 来源 | 用途 |
|---|---|---|
| `primitive_id` / `primitive_version` | 原语 | 审计与回归 |
| `params_hash` | 工位绑定参数 | 复现某次判定 |
| `model {name, version}` | 原语内部 | 模型可追溯 |
| `confidence` | 原语校准后输出 | 引擎阈值 |
| `correlation_key` | 事件类型定义 | 多相机去重/冲突 |
| `evidence_refs` | 原语 | 关键帧/片段 |

**置信度规则**

- `confidence` 必须由原语在留出集上校准（可靠性曲线 / ECE），并记录校准版本；
- 不同原语的 confidence **不可比较、不可平均**（§8 已禁止）；
- 未校准的原语只能以 `NEEDS_REVIEW` 方式上线，或使用保守阈值。

**时序逻辑放哪**（避免三处重复）

| 逻辑 | 归属 |
|---|---|
| 帧级平滑、N-of-M、动作内部时序（如拧紧持续时长） | 原语内部 |
| 去抖、`stable_for_ms`、`within_ms`、属性聚合 | EventBuilder |
| 步骤完成/超时/汇合/状态规则 | 引擎（DSL 权威） |

原则：DSL 里声明的条件以引擎为准；原语内部平滑只负责“别产生抖动事件”，不能替代引擎判定。

## 6. 配置 vs 训练：新 SOP 怎么落地

| 场景 | 动作 | 成本 | 谁做 |
|---|---|---|---|
| L0 已有原语 + 已有参数 | 绑定 ROI/阈值 | 分钟 | 实施 |
| L1 已有原语，新对象/新状态 | 少量标注、微调或模板 | 小时–天 | 视觉工程 |
| L2 已有原语族，新动作类 | 采集标注视频、训练 | 天–周 | 算法 |
| L3 新原语 | 设计契约 + 训练 + 评估 | 周 | 算法 |
| L4 零样本 VLM | 作为 EventBuilder 适配器接入 | 小时，但精度/成本/时延需评估 | 研究 |

新 SOP 的标准流程：

1. 写/导入 DSL，每步 `completion` 引用事件类型；
2. 在目录里查事件类型；有则复用，没有则找匹配原语并新增目录条目（配置，不改代码）；
3. 没有原语能表达 → 按 L2/L3 立项，**不临时写一次性脚本**；
4. 用录制视频回放标定阈值，看事件级 precision/recall；
5. `validate → publish`，版本冻结；
6. 上线后用复核结果反哺阈值和目录。

> L4 不进入核心：VLM 只是一个事件来源。做得成是加速器，做不成不影响主线。

## 7. 评估与准入门槛

按**事件级**评估，不看帧级 mAP：

| 指标 | 含义 | 完成类事件门槛 | 辅助类事件门槛 |
|---|---|---|---|
| precision | 报出来的事件有多少是真的 | ≥ 0.99 | ≥ 0.95 |
| recall | 真实事件被捕捉到的比例 | ≥ 0.95 | ≥ 0.90 |
| latency p95 | 实际发生 → 事件产出 | ≤ 500 ms（可配置） | ≤ 1 s |
| false events/min | 每分钟误报 | 0（验收场景） | 记录并观察 |
| 误完成率 | 不该完成却完成步骤 | **验收必须为 0** | — |

SOP 场景里**误报比漏报危险**：误报会错误完成步骤，漏报只是超时进复核。所以完成类事件用高 precision 门槛，低置信度一律 `NEEDS_REVIEW`。

每个原语维护一组**黄金视频**，任何模型/参数变更都跑回归。

## 8. 实验室验证矩阵

用可控制场景验证“原语边界”，不是验证产线精度：

- 3 个原语家族各选 1 个：`object_placed`（摆放）、`pose_action`（动作）、`fastening_action` 或 `surface_inspection`（难事件）；
- 2 台相机（俯视 + 侧视），至少 1 个动作双机位可见；
- 3 名操作者 × 10 遍，人工按时间戳标注真值；
- 先用手工标注事件跑引擎（验证判定链路），再用自动检测对同一份真值算 precision/recall（验证检测链路）。

产出：每个原语的训练成本、误报率、对机位/光照的敏感度，以及事件目录 v0 的候选集。

## 9. 与现有架构的落点

| 内容 | 路径 | 阶段 |
|---|---|---|
| 事件类型目录 | `contracts/catalog/*.yaml` | 阶段 1（schema + 模拟事件） |
| 原语实现 | `runtime/primitives/` | 阶段 2 起 |
| EventBuilder | `runtime/event_builder.py` | 阶段 2 |
| 黄金视频/评测 | `tests/scenarios/`、`runtime/eval/` | 阶段 2 起 |
| SOP 编辑器的“事件选择器” | 前端后续 | 阶段 5 前 |

阶段 1 仍然只用模拟事件，本文件不增加阶段 1 的实现范围。阶段 2 先落 2–3 个原语，验证 §8。

## 10. 不做什么

- 端到端学习一个 SOP（不可审计、数据成本高、泛化差）；
- 原语跨相机、做几何融合（留在 §8 后续能力）；
- 原语直接推进 SOP 状态（必须经过事件与引擎）；
- 从视频自动生成 DSL（独立课题，不混入主线）；
- 为单个 SOP 写一次性检测脚本。

## 11. 待确认问题

| # | 问题 | 影响 | 何时确认 |
|---|---|---|---|
| P1 | 先做哪 2–3 个原语 | 阶段 2 范围 | 实验室测试前 |
| P2 | 标注工具与数据集版本管理 | 训练成本、可复现性 | 阶段 2 前 |
| P3 | 置信度校准方法（单标量是否够） | 阈值与复核率 | 首个原语落地前 |
| P4 | 外部信号接入方式（PLC/OPC-UA/扫码） | 决定“任意 SOP”边界 | 阶段 3 前 |
| P5 | 是否引入 DSL v2 属性谓词 | 目录规模 | 目录条目数超过阈值时 |
| P6 | 每个原语的证据要求（keyframe/clip） | 存储与复核 | 阶段 2 前 |

## 附录 A：实验室 SOP 映射示例

| 步骤 | DSL `completion` 事件类型 | 原语 | 参数 |
|---|---|---|---|
| 放置底板 | `base_placed` | `object_placed` | base_plate → Z1, stable 500ms |
| 装左件 | `left_part_placed` | `object_placed` | red_block → Z2L |
| 装右件 | `right_part_placed` | `object_placed` | blue_block → Z2R |
| 双手确认 | `both_parts_present` | `count_threshold` | Z2, n=2 |
| 清洁（可选） | `surface_wiped` | `pose_action` | wipe, Z1 |
| 拧紧（难事件） | `fastener_tightened` | `fastening_action` | tool, Z2 |

同一份 SOP 用 3 个原语 + 2 个参数化事件类型即可表达，说明原语层的复用假设成立。
