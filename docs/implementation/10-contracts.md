# 10 契约（contracts）

**基线**：§5.2、§7 事件分层与字段、§11.2 WS 信封、§4.1 模块边界
**约束参考**：§5.1（类型安全、版本兼容、隔离）
**阶段**：0–1
**依赖**：无（新增 uv workspace 成员）

## 落点

```text
contracts/
├── pyproject.toml            # 包名 contracts；依赖 pydantic
└── contracts/
    ├── __init__.py
    ├── version.py            # SCHEMA_VERSION
    ├── enums.py              # 事件类型、处理结果、相机角色、消息类型
    ├── events.py             # Observation / VisionEvent / RoutedSOPEvent
    ├── catalog.py            # 事件类型目录：每类的必需 attributes 与 schema
    └── ws.py                 # WebSocketMessage
```

- 根 `pyproject.toml` 的 `[tool.uv.workspace].members` 增加 `contracts`。
- `backend/pyproject.toml`、`runtime/pyproject.toml` 增加依赖 `contracts` 与 `[tool.uv.sources] contracts = { workspace = true }`。
- 根脚本（lint / type / test）覆盖新成员。

## 分层（基线 §7.1）

```text
Observation → VisionEvent → RoutedSOPEvent → 状态机
```

- `Observation`：单次观测，允许 `execution_id` 为空；默认不落库。
- `VisionEvent`：候选事件，未绑定执行实例。字段按 基线 §7.2：
  `schema_version`、`event_id`、`event_type`、`station_id`、`camera_id`、`occurred_at`（带时区）、`emitted_at`、`frame_seq`、`confidence`、`model{name,version}`、`observation_ids`、`evidence_refs`、`attributes`。
- `RoutedSOPEvent`：已绑定执行实例。`execution_id` 非空，附 `resolution_method`、`resolved_at`、`resolver_rule_version`、`candidate_ids`、`reason_code`。
- 处理结果枚举：`ACCEPTED`、`DUPLICATE`、`QUARANTINED`、`REJECTED`（基线 §7.4）。

## attributes 的类型安全（基线 §7.5）

- 事件类型必须在 `catalog.py` 注册；每个类型定义必需 attributes 的 Pydantic 模型与版本。
- 校验时按 `event_type` 选择模型；未知类型 → `REJECTED`；缺必需键/类型错误 → `REJECTED`；无法确定执行归属 → `QUARANTINED`。
- 允许追加式可选字段以保持向后兼容；破坏性变更提升 `schema_version` 并提供迁移说明。

## WebSocket 信封（基线 §11.2）

```json
{
  "schema_version": "1.0",
  "message_id": "uuid",
  "type": "alarm.created",
  "occurred_at": "2026-10-27T10:12:03.510Z",
  "station_id": "station-01",
  "payload": {"alarm_id": "alarm-001", "severity": "HIGH"}
}
```

- 只推状态变化、告警、运行时健康与执行进度；不推帧。
- `message_id` 供客户端去重；断线后由 REST 快照补齐。

## 不做

- 不放业务判定、状态机、ORM、数据库类型；
- 不生成 TypeScript；前端 REST 类型来自 OpenAPI（基线 §11），WS 消息阶段 1 手写最小类型。

## 测试

- 每类事件：合法样例通过；缺字段、无时区、错误 attributes 被拒绝；未知类型被拒绝。
- 向后兼容：旧样例在新增可选字段后仍通过。
- `RoutedSOPEvent` 缺 `execution_id` 或 `resolver_rule_version` 必须失败。
- WS 信封缺 `message_id` / `schema_version` 必须失败。

## DoD

`uv run pytest contracts/tests` 通过；backend 与 runtime 能导入 contracts；`scripts/generate-client.sh` 不受影响。
