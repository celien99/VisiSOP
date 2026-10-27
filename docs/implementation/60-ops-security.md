# 60 可靠性、安全与运维

**基线**：§9.3 证据访问、§13 健康与告警、§15.2–15.3 部署与权限、§16 保留与可观测
**约束参考**：§12、§13、§19.2
**阶段**：1（健康/日志/角色桩）/ 阶段 5（对账、保留、完整权限）
**依赖**：30、50

## 落点

```text
backend/app/core/security.py        # 角色枚举、当前用户依赖（dev 桩）
backend/app/application/health.py   # 健康聚合、运行时注册
backend/app/workers/                # outbox dispatcher、超时扫描、证据对账、保留清理
compose.yml                         # 阶段 2 增加 runtime 服务
```

## 健康（基线 §13.1）

- 统一枚举：`UNKNOWN`、`STARTING`、`HEALTHY`、`DEGRADED`、`UNAVAILABLE`、`MISCONFIGURED`、`STOPPED`。
- 相机、Runtime、模型推理、数据库/平台分开记录，写 `runtime_health_events`；不得把断流误判为漏步。
- `GET /health/summary` 返回各组件；变化记录 `component_type`、`component_id`、`runtime_id`、`previous_status`、`current_status`、`reason_code`、`occurred_at`。
- Runtime 注册 `runtime_id`、相机列表、版本与心跳；超时未心跳 → `UNAVAILABLE`。

## 告警（基线 §13.2–13.3）

`PROCESS_COMPLIANCE`、`VISION_QUALITY`、`DEVICE_HEALTH`、`INFERENCE_HEALTH`、`PLATFORM_HEALTH`、`CONFIGURATION`；`severity` 与 `status` 分离。人工复核必须有原因码、操作者、决定、理由与证据，且保留原始模型输出。

## 安全（基线 §15.3）

- 角色 `VIEWER` / `OPERATOR` / `ENGINEER` / `ADMIN`，统一策略检查，不散落在路由。
- `APP_ENV=development` 才允许关闭认证；生产缺少认证配置时启动失败。
- 证据接口鉴权 + 工位权限 + 保留状态检查；禁止公开目录或本地路径直出（基线 §9.3）。
- 相机凭据、RTSP 地址、令牌脱敏；日志与错误响应不得包含。
- 写操作全部审计：SOP 发布、配置修改、执行启停、告警确认/关闭、人工复核。

## 一致性任务（基线 §9）

- Outbox dispatcher：提交后发布 WS/外部通知，失败可重试；未投递数量作为指标。
- 超时扫描：按 `deadline_at` 推进 `TIMED_OUT`。
- 证据对账：修复孤儿文件、缺失文件、`PENDING_VERIFY` 卡住项。
- 保留清理：dry-run、删除统计、失败重试、审计；legal hold 优先；删证据不删审计元数据。

## 指标（基线 §16）

每路相机 FPS、采样 FPS、推理延迟、事件生成延迟、发送失败/重试数、丢帧数、Runtime 重启次数、DB 连接状态、Outbox 未投递数、证据缺失数、人工复核积压量。

日志字段：`station_id`、`camera_id`、`execution_id`、`event_id`、`runtime_id`、trace/request ID。

## 部署（基线 §15）

- PoC：web、api、video-runtime、postgres、`evidence/` 目录；Compose 管通用服务，相机 SDK/GPU 冲突时 runtime 可宿主机运行。
- 数据库与证据目录必须持久化卷；所有服务暴露健康/readiness。
- 生产补充备份恢复、时间同步、日志轮转、容量告警、升级回滚。

## 不做（阶段 1）

Prometheus/Grafana 全套、SSO、mTLS；先用结构化日志 + `/health/summary` + `runtime_health_events`。

## 测试

认证开关（生产缺配置启动失败）、健康聚合隔离、Runtime 心跳超时、保留 dry-run、证据对账修复、故障注入（断线/DB 暂不可用/队列积压）。

## DoD

故障注入用例全部通过；日志与审批字段可断言；README 补充健康检查、恢复与备份步骤。
