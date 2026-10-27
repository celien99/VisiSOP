# AI-SOP 实现拆分

## 规范分层

| 层 | 文档 | 作用 |
|---|---|---|
| 架构基线 | `docs/AI_SOP_Platform_Architecture_v2.0.md` | 系统如何运行：进程边界、模块、数据模型、API 面、运行时选型、实施阶段 |
| 约束参考 | `docs/AI_SOP_Architecture_Design_v1.1.md` | 基线未展开的严格不变量：状态迁移矩阵、执行关联细节、保留策略、安全边界 |
| 缺陷与裁决 | `docs/adr/0001-architecture-baseline-review.md` | 已发现的矛盾、缺失、不可实现项及修订 |
| 实现简报 | 本目录 | 落到当前仓库的路径、交付物、依赖、测试与 DoD |

**冲突时以架构基线为准**；约束参考只在基线未覆盖处生效。新发现的矛盾先补 ADR，不得静默选边。

基线不逐段复制到本目录。复制会产生两份规范，第一次修改就漂移；拆分只发生在实现层。版本间的差异只记在 ADR-0001，本目录不做版本对照。

## 如何阅读架构基线

先读 §1–2（问题、部署形态、进程边界）和 §22（最终基线），共约 5 页，建立全局。然后按工作包读：

| 工作包 | 必读 | 选读 |
|---|---|---|
| 10 契约 | §7.1–7.4 事件分层与字段、§11.2 WS 信封 | §5.2 |
| 20 领域与 SOP 引擎 | §5 领域模型、§6 DSL 与状态机、§8 多相机 | v1.1 §6.4.1 迁移矩阵 |
| 30 后端 | §2、§5、§7、§9 一致性、§10 表与索引、§11.1 API 清单 | v1.1 §19.3 |
| 40 前端 | §11.3 预览 vs 证据、§13 告警与复核、§14 页面 | §15.3 |
| 50 运行时 | §2.2 进程边界、§3 开源吸收、§12 管线与接口、§15 | §19 |
| 60 运维安全 | §9、§13、§15.2–15.3、§16、§19 | v1.1 §12–13 |
| 70 测试 | §17 测试层与验收、§18 阶段 | §19 |

不要从 §4 的目录树逐字复制。它描述的是理想单仓布局；本仓库已有骨架，映射见 D9。基线已注明该层可省略。

## 工作包

| ID | 简报 | 仓库落点 | 依赖 | 基线章节 | 阶段（基线 §18） |
|---|---|---|---|---|---|
| 10 | [契约](10-contracts.md) | `contracts/` | — | §7、§11.2 | 阶段 0–1 |
| 20 | [领域与 SOP 引擎](20-domain-sop-engine.md) | `backend/app/domain/`、`sop_dsl/` | 10 | §5、§6、§8 | 阶段 1A（线性）+ 1B（并行/可选/多相机） |
| 30 | [后端持久化与 API](30-backend.md) | `backend/app/{models,application,infrastructure,api}`、`backend/app/alembic/` | 10、20 | §2、§5、§7、§9–11、§13 | 阶段 1A + 1B 补端点 |
| 40 | [前端](40-frontend.md) | `frontend/src/` | 10、30 | §11、§13、§14 | 阶段 1 最小页 / 阶段 2–5 完整 |
| 50 | [视频运行时](50-video-runtime.md) | `runtime/` | 10 | §3、§12、§15 | 阶段 2 |
| 60 | [可靠性、安全与运维](60-ops-security.md) | `backend/app/{core,workers}`、`compose.yml` | 30、50 | §9、§13、§15、§16 | 阶段 1 基础 / 阶段 5 完整 |
| 70 | [测试与验收](70-testing-acceptance.md) | `backend/tests/`、`tests/scenarios/` | 20+ | §17、§18 | 贯穿 |

## 实施顺序

```text
10 契约 ──► 20 SOP 引擎 ──► 30 后端 ──► 40 前端
   │                           ▲
   └────────► 50 视频运行时（阶段 2）┘

60 跨 30/50；70 从 20 开始，随各包推进
```

- 10 最先做：事件 schema 是 20 的输入、50 的输出。
- 20 可与 30 的骨架并行，但 30 的用例层依赖 20 的纯函数接口。
- 40 依赖 30 的路由契约；路由定型前可用 mock 数据先搭页面。
- 50 在阶段 2 才开工；阶段 1 用模拟事件生产者（基线 §18 阶段 1）。

## 仓库映射与裁决记录

下表只保留**仓库落地层**的选择：目录、包边界、技术选型。架构语义（状态机、证据、隔离、API 行为）一律以基线为准，不在此复述——复述即漂移。改动需 ADR。

| # | 裁决 | 理由 / 出处 |
|---|---|---|
| D1 | 持久化继续用 SQLModel，不引入原生 SQLAlchemy 模型 | 骨架已选定；SQLModel 构建在 SQLAlchemy 2.x 之上。`domain` 仍不得导入 SQLModel（基线 §4.1） |
| D2 | `contracts/` 作为根 uv workspace 成员；`backend` 与 `runtime` 通过 workspace source 依赖它 | 基线 §4“共享契约包”，不复制 schema（A28） |
| D3 | SOP 状态机是纯函数；PostgreSQL 是唯一权威状态；每次迁移乐观锁落库 | 基线 §9.1 |
| D9 | 不新建 `apps/` 层：`apps/web`→`frontend/`，`apps/api`→`backend/`，`packages/contracts`→`contracts/`，`runtime/`→`runtime/`，`sop_dsl/`→`sop_dsl/` | 沿用现有骨架；基线 §4 已注明 `apps/` 可省略 |
| D10 | `sop_dsl/` 作为独立 workspace 成员，放 schema + 静态校验；执行引擎留在 `backend/app/domain/sop/` | 校验器被 API、配置、测试共用，不依赖后端 |
| D15 | 阶段 1 不建工位→SOP 绑定表；执行创建时显式选择版本 | 基线 §11.1；O1 确认前不引入未确认语义 |
| D17 | 阶段 1 假定 runtime 与 backend 同机共享 `EVIDENCE_DIR`；跨机部署改为上传接口 | 基线 §9.2、O4；决定证据交接方式的前提 |
| D18 | API 不设版本段：`API_PREFIX = "/api"`，替换骨架的 `/api/v1` | 单机同源部署，无需并行多版本；生成客户端与文档不出现版本段 |

已升级为架构条目的旧裁决（勿在此重新解释）：D4→A25 阶段 1B、D5→A14 `deadline_at`、D6→A4 隐式激活、D7/A1 无 `current_step_key`、D8/A5 投影、D11/A28 事件目录、D12→§9.2 证据生命周期、D13→A10、D14→A7 显式执行 API、D16→A9 隔离改绑。

## 阶段 1 闭环路径（可演示的最小链路）

这条链路跑通，才算阶段 1 闭环：

1. 创建 `station`、`camera`、`station_camera_binding`；
2. `POST /sops` 建草稿 → `POST /sops/{id}/validate` → `POST /sops/{id}/publish` 产出不可变版本；
3. `POST /stations/{station_id}/executions`（带 `sop_version_id`）→ `CREATED → RUNNING`；
4. 夹具或 `/events` 投递 `VisionEvent` → receipts 去重 → resolver 绑定 → `engine.apply` → `step_executions` / `alarms` / `outbox` 同事务；
5. `GET /executions/{id}/timeline` + WS 推送 → 前端显示步骤状态与告警；
6. 告警 `acknowledge` / `resolve`；重复 `event_id` 返回 `DUPLICATE`；无活动执行时返回 `QUARANTINED` 并可 `assign`；
7. 全程无真实相机、无模型：事件由 JSON 脚本产生（70 的场景夹具）。

阶段 2 把第 4 步的输入从脚本换成 `runtime/`，其余步骤不变——这就是“模型可替换、业务核心不动”的可验证含义。

## 待确认问题（阶段 1 默认值）

| # | 问题 | 阶段 1 默认 | 何时必须确认 |
|---|---|---|---|
| O1 | 执行周期如何开始/结束 | 显式 API 开始，状态机或操作员结束 | 阶段 3 接条码/PLC 前 |
| O2 | 可选步骤的跳过条件语法 | `skip_if.all_steps_completed` / `skip_if.event_type` | 首个真实 SOP 配置前 |
| O3 | 生产身份提供方 | dev 角色桩 | 阶段 5 前 |

## 阶段边界

| 阶段 | 交付 | 明确不做 |
|---|---|---|
| 1A | 线性 DAG、超时、复核、事件闭环、最小 UI；模拟事件驱动 | 真实相机与模型 |
| 1B | 并行/可选/汇合、多相机规则，及对应端点与页面 | — |

全阶段不做：

- 真实相机、实时预览、DeepStream/Osprey、SOP Monitoring Blueprints（阶段 3–4 的独立 Spike）；
- 跨相机几何融合/标定、VLM 判定；
- 完整认证提供方（仅 dev 回环 + 角色桩）；
- SOP 图形化编辑器（先校验 + 发布 + 只读 DAG 展示）；
- 原始视频与 `Observation` 长期存储。

## 完成定义（每个工作包通用）

1. 约束参考 §6.5 / §11 / §13 与基线 §4.1 的“不允许的实现”一条未犯；
2. 相关测试、`mypy`/`ty`、`ruff`、前端 lint 实际执行并汇报结果；
3. 新增/修改的接口同步更新了对应简报的落点清单。
