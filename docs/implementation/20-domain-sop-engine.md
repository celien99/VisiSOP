# 20 领域模型与 SOP 引擎

**基线**：§5 领域模型、§6 版本化 DSL 与 DAG 状态机、§8 多相机关联
**约束参考**：§6.4.1 迁移矩阵、§6.4.2 并行/可选、§6.4.3 证据关联
**阶段**：1
**依赖**：10（事件类型）

## 落点

```text
sop_dsl/                        # 独立 workspace 成员（D10）
├── pyproject.toml
└── sop_dsl/
    ├── schema.py               # DSL v1 的 Pydantic 严格 schema
    ├── validate.py             # §6.2 静态校验
    └── examples/*.yaml

backend/app/domain/
├── __init__.py
└── sop/
    ├── model.py                # SOPGraph / StepSpec / ExecutionState / StepState
    ├── compiler.py             # sop_dsl → 不可变 SOPGraph（含依赖边、join）
    ├── engine.py               # 纯函数迁移
    └── correlation.py          # 单/多相机证据匹配、角色优先级、冲突判定
```

`domain` 不得导入 FastAPI、SQLModel、SQLAlchemy、OpenCV、PyTorch、DeepStream（基线 §4.1）。

## DSL v1（以 基线 §6.1 为准）

步骤字段：`key`、`name`、`type`（`ACTION` / `CHECKPOINT`）、`required`、`depends_on`、`timeout_ms`、`completion`、`evidence`、`join_policy`（仅汇合节点）。

- `completion.mode`：
  - `EVENT_RULE`：`all` / `any` / `not` + 白名单操作符 `event_type`、`min_confidence`、`stable_for_ms`、`within_ms`、`source_camera_role`；
  - `STATE_RULE`：阶段 1 仅支持 `all_steps_completed` 与 `any_steps_completed`。
- `join_policy`：
  - `"ALL_REQUIRED"`；
  - `{ "type": "ANY_OF_N", "n": 1 }`（Pydantic discriminated union；`n` 必须 ≤ 依赖数）。
- 可选步骤：`required: false`，必须声明 `skip_if`，阶段 1 仅支持：
  - `{ "all_steps_completed": ["key", ...] }`
  - `{ "event_type": "..." }`

  跳过必须写审计原因（O2 待业务确认，但语法先固定，避免 20b 停工）。
- 禁止内嵌任意代码；拒绝未知字段；发布时生成不可变快照 + 内容哈希。

## 引擎契约

```python
def apply(
    graph: SOPGraph,
    state: ExecutionState,
    event: RoutedSOPEvent,
    now: datetime,
) -> TransitionResult: ...

def timed_out(graph: SOPGraph, state: ExecutionState, now: datetime) -> list[StepTransition]: ...
```

- 纯函数：无 I/O、无全局状态、不读时钟；时间只来自参数 `now`。
- `ExecutionState` 含每个步骤的 `StepState`（状态、`activated_at`、`deadline_at`、匹配证据摘要、join 进度）。匹配证据由 30 从 `step_executions` / `event_evidence_links` 重建后传入。
- `TransitionResult`：步骤迁移列表、执行状态迁移、待建告警（含 `reason_code`）、判定理由、规则/DSL 版本。
- 同一输入必须得到同一输出；禁止依赖集合遍历顺序。

## 状态（基线 §6.3）

- 步骤：`PENDING`、`ACTIVE`、`COMPLETED`、`FAILED`、`SKIPPED`、`TIMED_OUT`、`NEEDS_REVIEW`。
- 执行：`CREATED`、`RUNNING`、`PAUSED`、`COMPLETED`、`ABORTED`、`NEEDS_REVIEW`。
- 迁移矩阵以 约束参考 §6.4.1 为底稿，`IN_PROGRESS` 换成 `ACTIVE`，超时落到 `TIMED_OUT`；迟到事件不回退已完成状态。
- 隐式激活与原子完成见 A4；活动步骤由 `step_executions` 派生（A1），不存单值当前步骤。

## 多相机关联（基线 §8）

- 按 `station_id`、相机角色、事件类型、时间窗口筛选；窗口由步骤/事件策略配置。
- 完成规则可要求：指定角色、最少独立证据数、主证据来源、最大时间差。
- 多相机重复检测按 `correlation_key` 去重；证据不足证明同一动作时不得因时间接近删除。
- 不平均置信度；冲突按显式优先级处理，无规则则 `NEEDS_REVIEW`。
- 每次判定记录输入事件 ID、相机 ID、规则版本、`reason_code`。

## 增量交付（A25）

| 子步 | 内容 | 门槛 |
|---|---|---|
| 20a | 线性 `depends_on`、`EVENT_RULE all/any`、超时、迟到、幂等 | 迁移矩阵全绿 |
| 20b | 并行分支、`ALL_REQUIRED` / `ANY_OF_N`、可选步骤与跳过审计 | 汇合与跳过场景全绿 |
| 20c | 相机角色、多相机去重与冲突、`stable_for_ms` / `within_ms` | 冲突必进 `NEEDS_REVIEW` |

三个子步都完成才算阶段 1 的 20 完成；20a 可先解锁 30。

## 不做

- 几何标定/重建、跨相机深度融合、VLM 结果解释；
- 持久化、事件去重（由 30 的 `event_processing_receipts` 负责）；
- 读取数据库、看时钟、发 WebSocket。

## 测试（基线 §17.1）

- 迁移矩阵表驱动；并行汇合（ALL/ANY_OF_N）；可选步骤跳过与审计；
- 同一事件重放状态不变；迟到事件不回退；多工位互不影响；
- 多相机冲突 → `NEEDS_REVIEW`；证据不足不判合格；
- DSL：有环、悬空引用、未知字段、任意代码、非法范围全部拒绝；
- 确定性：同一输入重复执行结果逐字段相等。

## DoD

分支覆盖率 90%+；`mypy`/`ty` 严格通过；除 contracts 与 sop_dsl 外无第三方运行时依赖。
