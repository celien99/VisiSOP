# ADR-0001：架构基线评审与修订

- **状态**：已接受（实施用）
- **日期**：2026-10-27
- **影响文件**：`docs/AI_SOP_Platform_Architecture_v2.0.md`（已应用本 ADR 的修订）、`docs/AI_SOP_Architecture_Design_v1.1.md`（降为约束参考并标注取代项）、`docs/implementation/*`

## 背景

v2.0 是架构设计文档，v1.1 是约束文档。两份文档叠加后仍存在**自相矛盾、缺失、不可实现**三类问题。若直接进入实现，Agent 必然在矛盾处自行二选一，并把它写成代码。

本 ADR 只记录缺陷与裁决，不重复文档正文。所有修订已落回基线对应章节。

## 缺陷与裁决

| # | 位置 | 类型 | 问题 | 裁决 |
|---|---|---|---|---|
| A1 | v1.1 §4.6 | 矛盾 | `SOPExecution.current_step_key` 是单值，但 §6.4.2 允许并行步骤同时进行 | 删除该字段；活动步骤由 `step_executions` 派生 |
| A2 | v1.1 §4.5 vs §6.4.2 | 矛盾 | `next` 与 `depends_on` 两套流程表示，可生成互相冲突的图 | 只保留 `depends_on`；`next` 删除 |
| A3 | v1.1 §4.5 | 冗余 | `PARALLEL_GROUP` / `OPTIONAL` 与 `required`、DAG 并行重复 | 步骤类型收敛为 `ACTION` / `CHECKPOINT`；可选靠 `required: false` + `skip_if` |
| A4 | v1.1 §6.4.1 | 不可实现 | 进入 `IN_PROGRESS` 要求“开始证据”，但单事件步骤没有开始证据 | 允许隐式激活；瞬时事件允许 `PENDING → COMPLETED` 原子迁移 |
| A5 | v2.0 §5.1 vs §10 | 矛盾 | ER 图有 `StationRuntimeState`，表清单没有 | 定义为可重建投影，不建表 |
| A6 | v2.0 §15.2 vs §11.1 | 缺失 | 要求 Runtime 注册/心跳，但没有任何注册端点 | 增加 `/runtimes/register`、`/runtimes/{id}/heartbeat`、`GET /runtimes` |
| A7 | v2.0 §11.1 | 缺失 | 创建执行实例没有定义请求体，也没有工位→SOP 绑定 | 阶段 1 必带 `sop_version_id`；不建绑定表（O1 现场确认后再定） |
| A8 | v2.0 §11.1 | 缺失 | 草稿无法读取/修改，validate/publish 缺闭环 | 增加 `GET/PATCH /sops/{id}`，仅草稿可改 |
| A9 | v2.0 §7.3 | 不完整 | 事件只能进隔离，没有出隔离的命令 | 增加 `GET /events?status=...` 与 `POST /events/{id}/assign`，写审计 |
| A10 | v2.0 §9.2 vs §12.1 | 跨进程缺口 | 证据由 runtime 捕获，生命周期却按 backend 单进程描述 | 阶段 1 共享 `EVIDENCE_DIR/tmp/`；分离部署改上传接口 |
| A11 | v2.0 §6.1 | 缺失 | `stable_for_ms` 需要历史证据，没有持久化模型 | `step_executions.matched_event_ids`（JSONB）保存参与判定的 `event_id` |
| A12 | v2.0 §6.3 | 歧义 | `TIMED_OUT` 是否终态、迟到证据能否补救未定义 | 对自动迁移为终态；迟到证据只能补证据或进 `NEEDS_REVIEW` |
| A13 | v2.0 §6.3 | 不可实现 | `STATE_RULE` 与汇合节点没有触发时机，CHECKPOINT 永远不会完成 | 每次步骤/执行迁移后重新评估下游节点，另加定时扫描 |
| A14 | v2.0 §6.1 | 歧义 | `timeout_ms` 从何时起算、暂停是否计时未定义 | 从激活起算；`activated_at`/`deadline_at` 落库；暂停累计不计时 |
| A15 | v2.0 §8 | 不可实现 | “相机冲突”没有定义，无法写判定逻辑 | 定义为同一 `correlation_key` 的互斥结论；给出独立证据定义 |
| A16 | v2.0 §6.1 | 缺失 | `FAILED` 在 DSL 中不可达 | 增加可选 `failure` 规则；未声明则只能人工复核产生 |
| A17 | v2.0 §13.3 | 不一致 | `reason_code` 无封闭枚举，审计与 UI 会漂移 | 定义最小枚举（见 §13.3） |
| A18 | v2.0 §7.2 | 悬空引用 | `observation_ids` 指向默认不落库的 observations | 仅保留 observation 时才填；否则为空数组 |
| A19 | v2.0 §10 | 职责重叠 | `vision_events.event_id` 唯一与 `event_processing_receipts` 关系不清 | 前者存已接收事件，后者存最终处理结果；唯一键均为 `event_id` |
| A20 | v2.0 §11.1 | 缺失 | 相机 start/stop 不知道由哪个 Runtime 执行 | `cameras.runtime_id` 指定；无 runtime 返回 503 + 设备告警 |
| A21 | v2.0 §11.1 | 缺失 | 有执行详情，没有执行列表，历史页无法分页查询 | 增加 `GET /executions?station_id=&status=&from=&to=` |
| A22 | v2.0 §13.3 | 缺失 | 人工复核/跳过只有描述，没有命令端点 | 增加 `POST /executions/{id}/steps/{key}/review|skip` |
| A23 | v2.0 §15.3 | 安全缺口 | Runtime→API 只讲了用户角色，没有服务间认证 | 独立 service credential，权限仅限 ingest/evidence/heartbeat |
| A24 | v2.0 §7.4 | 正确性 | 跨相机排序依赖设备时钟，没有同步要求 | 相机内以 `frame_seq` 为准；跨相机只做容差窗口；要求 NTP |
| A25 | v2.0 §18、§1.1、§10 | 交付风险 | 阶段 1 同时要求并行/可选/多相机/18 张表，与 PoC 定位不符 | 阶段 1 拆 1A（线性闭环）/1B（并行/可选/多相机）；暂缓 4 张表 |
| A26 | v2.0 §17.2 | 验收风险 | 全是定性标准，无法判断“做完了” | 增加本地 PoC 量化门槛（§17.2） |
| A27 | v2.0 §15.2 | 运维风险 | 证据不可逆丢失，备份却排到生产阶段 | 阶段 2 必须做一次 DB + 证据目录恢复演练 |
| A28 | v2.0 §7 | 版本化缺口 | 事件目录变更没有兼容策略 | 事件类型在 contracts 注册；只允许追加可选字段；破坏性变更升版本并双发 |

## 影响

- **架构基线**：上述修订已写入对应章节；§4 目录树增加“可省略 apps/ 层”的说明；§6/§7/§8/§9/§10/§11/§13/§15/§16/§17/§18/§21 均有增补。
- **v1.1**：降为约束参考；被取代的 5 个条目在页首列出并在原文位置标注。
- **实现拆分**：架构语义以基线为准；`docs/implementation/README.md` 只保留仓库映射裁决，不再重复架构规则。
- **阶段 1 范围**：1A = 线性 DAG、超时、复核、事件闭环、最小 UI；1B = 并行/可选/汇合、多相机规则。1B 不得跳过，但可以晚于 1A 的端到端演示。

## 未决问题（不由 Agent 假设）

- 执行周期的真实起点（人工/条码/PLC）——阶段 3 前确认；
- 可选步骤跳过的业务语义——首个真实 SOP 前确认；
- 工位与 SOP 的绑定方式——阶段 5 前确认；
- 运行时与后端是否同机——阶段 2 前确认（决定证据交接方式）。

## 后果

- 文档不再“看起来都对但无法同时实现”；
- 后续会话以架构基线与本 ADR 为准，发现新矛盾先补 ADR，不静默选边；
- 阶段 1 的交付面缩小到可演示、可验收，算法与硬件风险仍留在阶段 2–4。
