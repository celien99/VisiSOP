# 30 后端：持久化、用例与 API

**基线**：§2 部署形态、§5 领域模型、§7 事件关联、§9 一致性、§10 表与索引、§11 API
**约束参考**：§19.2 保留策略、§19.3 关联细则
**阶段**：1
**依赖**：10、20（引擎接口）

## 落点

```text
backend/app/
├── models/           # 由 models.py 改为包；__init__ 汇总导出，alembic 目标仍是 app.models
├── application/      # 用例：事件接入、执行编排、告警、证据、outbox、超时扫描、运行时注册
├── infrastructure/   # 仓储、EvidenceStore 本地实现、OutboxDispatcher、RuntimeClient
├── workers/          # 后台轮询入口（outbox、超时、对账、清理）
└── api/routes/       # 见下方 API 清单
```

`backend/app/models.py` 改为同名包即可，Alembic 的 metadata 目标与 `alembic/env.py` 无需改动。

## 表（基线 §10，阶段 1 全建）

`stations`、`cameras`、`station_camera_bindings`、`sop_definitions`、`sop_versions`、`sop_step_definitions`、`sop_step_dependencies`、`sop_executions`、`step_executions`、`observations`（可选索引，默认不写）、`vision_events`、`event_processing_receipts`、`evidence_assets`、`event_evidence_links`、`alarms`、`outbox_messages`、`audit_records`、`runtime_health_events`。

- 唯一约束：`vision_events.event_id`；`(sop_version_id, step_key)`；`(execution_id, step_key)`；`(sop_id, version)`；`stations.code`；告警去重键（execution + step_key + category + 未关闭）。
- 索引：`sop_executions(station_id, status)`、`alarms(status, severity, created_at)`、`evidence_assets(sha256)`（基线 §10.1）。
- 并发：`sop_execution.version` 乐观锁；冲突重读重试一次，仍冲突返回 409 或隔离。
- 时间：全用 `TIMESTAMPTZ` 存 UTC；`sop_executions` 带 `started_at`、`finished_at`、`accept_events_until`、`paused_at`、`total_paused_ms`。
- `StationRuntimeState` 是投影表/视图，可随时重建（A5），不得成为判定依据。

## 一次事件接入（基线 §7、§9.1）

```text
校验 envelope → 查 receipts 去重 → ExecutionResolver → 重建执行快照
→ engine.apply → 同一事务写 step/execution/alarm/audit/outbox → 202 + 处理结果
```

- 处理结果：`ACCEPTED`、`DUPLICATE`、`QUARANTINED`、`REJECTED`；每次都写 `event_processing_receipts`。
- 关联：携带 `execution_id` 时校验工位、状态、时间窗；未携带时仅在“唯一活动执行 + 相机已绑定 + 时间窗内 + 无周期冲突”时自动关联；其余隔离，记录候选集、规则版本、原因码。终态执行只允许补充证据，不回退状态。
- 新执行开始必须来自显式命令、条码/工件识别或 PLC 信号；周期起点方式未定（基线 §21）→ `OPEN QUESTION`，阶段 1 用显式 API。
- 证据：runtime 写 `EVIDENCE_DIR/tmp/{event_id}.*` 并在 `evidence_refs` 中给出键（A10）；backend 校验存在性 → SHA-256/尺寸 → 原子移动 → 建 `evidence_assets(PENDING_VERIFY)` → `AVAILABLE`；对账修复孤儿/缺失文件。
- 步骤证据窗口：`step_executions.matched_event_ids`（JSONB 数组）保存参与判定的 `event_id`，用于 `stable_for_ms` 重建与审计；不得只存聚合分数。
- 事务内只写 DB；提交后由 `OutboxDispatcher` 发 WS；前端重连走 REST 快照。

## API（基线 §11.1）

路径相对于 API 根，不设版本段；`API_PREFIX = "/api"`（D18），OpenAPI 与前端客户端已按此重新生成。

```text
GET/POST /stations
GET      /stations/{station_id}
GET      /stations/{station_id}/runtime-state
GET/POST /cameras
PATCH    /cameras/{camera_id}
POST     /cameras/{camera_id}/start|stop
GET      /cameras/{camera_id}/health

GET/POST /sops
GET/PATCH /sops/{sop_id}          # 仅草稿可改
POST     /sops/{sop_id}/validate|publish
GET      /sops/{sop_id}/versions

POST     /stations/{station_id}/executions
GET      /executions/{execution_id}
POST     /executions/{execution_id}/pause|resume|abort
GET      /executions/{execution_id}/timeline

GET      /alarms
POST     /alarms/{alarm_id}/acknowledge|resolve
GET      /evidence/{evidence_id}
GET      /health/summary

POST     /events                      # 运行时投递，幂等键 = event_id
GET      /events?status=QUARANTINED
POST     /events/{event_id}/assign    # 显式改绑，写审计（A9）
POST     /runtimes/register
POST     /runtimes/{runtime_id}/heartbeat
GET      /runtimes

GET      /ws                # 仅推状态/告警/健康
```

- 执行创建必带 `sop_version_id`（A7、D15）；工位已有 `CREATED`/`RUNNING` 实例时返回 409，必须显式中止或完成旧实例。
- 相机 `start`/`stop` 通过 RuntimeClient 转发；没有注册的 runtime 时返回 503 并记 `DEVICE_HEALTH` 告警，不得静默失败。
- `assign` 只能绑定同工位、未终态、时间窗内的执行；成功写 `audit_records` 与新 `event_processing_receipts`。
- 写操作走显式命令端点，不允许通用 PATCH 改状态；全部做授权与审计（60）。
- 统一错误体与分页；路由变更后运行 `bash scripts/generate-client.sh` 并提交生成物。

## 不做

- 认证提供方（60 给角色桩与中间件）；
- 多进程 outbox 抢锁（首版单 dispatcher，代码注明 `shortcut` 与升级时机）；
- 视频二进制入库；`observations` 默认不写；
- 客户端直连相机（启动/停止通过 RuntimeClient 转发）。

## 测试（基线 §17.1）

幂等（含 receipt）、乱序/迟到、并发推进、多工位隔离、关联隔离、Outbox 原子性、证据生命周期与对账、Alembic upgrade/downgrade、API 集成。

## DoD

`cd backend && uv run bash scripts/test.sh` 通过且覆盖率 ≥90%；§11.1 端点及运行时注册/心跳、隔离改绑端点全部有集成测试；OpenAPI 生成物无未提交 diff。
