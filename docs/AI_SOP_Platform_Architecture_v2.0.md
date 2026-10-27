# 工业 AI-SOP 多工位视觉监控平台：总体架构设计与开源项目吸收方案

> 版本：2.0（2026-10-27）  
> 状态：架构基线；在硬件与现场约束确认后冻结关键 ADR  
> 目标：实验台 PoC → 多工位试点 → 汽车座椅等生产线扩展  
> 设计原则：先定义真实系统如何运行，再规定 AI Coding Agent 如何修改它。本文不是单纯的编码约束清单。
>
> 评审发现的矛盾、缺失与不可实现条目及其修订见 `docs/adr/0001-architecture-baseline-review.md`。`AI_SOP_Architecture_Design_v1.1.md` 仅作约束参考，冲突条目已在其页首标注。

---

## 1. 这份架构要解决什么问题

平台通过多台相机持续观察多个装配工位，将图像/视频转换为可追溯的视觉证据与候选事件，再结合 SOP 工艺定义、执行上下文及可选的工具/PLC 信号，判断步骤是否完成、漏步、错序、超时或存在不确定情况。

系统必须从一开始区分四类事实：

1. **视觉事实**：模型检测到了什么、发生在何时、由哪台相机观察到。
2. **工艺事实**：哪个产品/工位正在执行哪个 SOP 版本，步骤当前处于什么状态。
3. **系统事实**：相机、推理进程、数据库和消息链路是否健康。
4. **证据事实**：哪张图片/哪段视频支持某次判定，证据是否完整、是否可访问。

不能把四类事实塞进一个 `status` 字段，也不能让模型直接决定并写入 SOP 最终状态。

### 1.1 首期目标

- 本地视频文件可驱动完整流程；不要求一开始就接入真实相机。
- 支持 1 个工位、1–2 台相机开始验证，领域模型不因扩展到多个工位而重写。
- 可在运行时启停相机源、调整采样策略，并显示相机/推理健康状态。
- SOP 支持版本、执行实例、步骤依赖、并行/可选步骤、超时与人工复核。
- 每个判定可以追溯到事件、规则版本、模型版本和证据。
- 断线、重复事件、迟到事件、重启、数据库短暂不可用都有明确处理策略。

### 1.2 首期不做

- 不建设完整 VMS/NVR，不长期保存所有原始视频。
- 不把 LLM/VLM 放在每一帧的实时关键路径上。
- 不引入微服务集群、Kafka、Redis、Kubernetes 或向量数据库，除非测量结果证明必要。
- 不允许 AI-SOP 取代安全 PLC 或作为危险设备安全联锁的唯一依据。
- 不先建设通用低代码工作流编辑器；首期采用版本化 SOP DSL 和可验证的配置界面。

---

## 2. 架构结论先行

### 2.1 推荐的部署形态

**采用“模块化单体业务后端 + 独立视频/推理运行时 + PostgreSQL + Web 前端”。** 不是每个模块一个微服务，也不是把视频采集、模型推理和 SOP 状态机都塞进一个 FastAPI 进程。

```text
┌──────────────────────────── Web 浏览器 ────────────────────────────┐
│ React + TypeScript                                                  │
│ 工位总览 │ 实时监控 │ SOP 编辑/发布 │ 告警中心 │ 执行历史 │ 证据回放 │
└────────────────────────────┬───────────────────────────────────────┘
                             │ HTTPS REST + WebSocket
┌────────────────────────────▼───────────────────────────────────────┐
│ Application API：FastAPI（模块化单体）                              │
│                                                                      │
│ API/鉴权 → Application Services → Domain → Repository               │
│                                                                      │
│ 工位/相机配置 │ SOP 版本 │ 执行协调 │ 事件路由 │ 判定 │ 告警 │ 审计   │
│ 证据元数据    │ Outbox    │ 历史查询 │ 实时状态投影 │ 健康状态        │
└───────────────┬──────────────────────────────┬──────────────────────┘
                │ SQLAlchemy                   │ Outbox Dispatcher
                ▼                              ▼
        ┌───────────────┐              ┌────────────────────┐
        │ PostgreSQL    │              │ WebSocket/Event    │
        │ 业务事实主库  │              │ 通知（可重放/重连） │
        └───────────────┘              └────────────────────┘

┌────────────────────── 独立 Video Runtime（一个或多个进程） ─────────┐
│ Source Adapter → Frame Sampler → Inference Pipeline → Event Builder │
│ 文件/RTSP/厂商 SDK   抽帧/ROI       模型/跟踪/时序       标准事件     │
│                         │                                            │
│                  Evidence Capture                                    │
│                         │                                            │
│  Runtime Health / Camera Health / Model Version / Backpressure       │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ 版本化事件契约：本机 HTTP（PoC）
                          │ 未来可替换为受控 IPC/消息中间件
                          ▼
                    Application API
```

### 2.2 进程边界的理由

- API 服务负责业务请求、配置、SOP 执行、持久化和查询；它不负责长期阻塞的视频读取循环。
- Video Runtime 负责视频源生命周期、解码、抽帧、推理和候选事件生成；它不直接修改 SOP 表。
- 两者通过带版本的消息契约通信。首期使用本机 HTTP/内部 API，避免过早引入消息中间件；事件发送失败必须重试或进入本地失败队列，不能静默丢失。
- PostgreSQL 是业务事实的唯一主库。前端展示状态是投影，不是事实来源。
- 证据文件保存在文件系统或对象存储，数据库只保存证据元数据、哈希和存储键。

### 2.3 为什么首期不拆微服务

当前主要不确定性在视觉可行性、SOP 判定规则、相机适配与现场部署，而不是业务服务数量。模块化单体可以保持事务一致性和调试简单，同时通过 Video Runtime 进程隔离推理负载。只有在不同模块出现明确独立扩缩容、独立团队交付或故障隔离需求时，才拆分服务。

---

## 3. 开源项目吸收策略：不是只列名字

以下项目承担不同层次的职责，不能互相替代。架构上要吸收它们解决问题的方式，而不是整套复制。

### 3.1 NVIDIA SOP Monitoring Blueprints：吸收“时序 SOP 识别”能力，不接管业务系统

项目：[`NVIDIA/sop-monitoring-blueprints`](https://github.com/NVIDIA/sop-monitoring-blueprints)

该项目提供 SOP 训练与推理微服务、时序动作分段和 VLM 相关流程，并包含用于 DeepStream SOP 推理服务的 Agentic Skills。它更接近“从视频识别 SOP 动作序列”的算法/推理参考实现，而不是一个完整的工厂业务平台。

**吸收方式：**

- 将其作为后续的 `Temporal SOP Recognizer` 候选实现，用于识别动作阶段、步骤片段或序列合规性。
- 把它的模型推理结果适配为本项目的 `Observation` / `VisionEvent`，不允许它直接写入本项目的 `SOPExecution`、`SOPStepResult` 或 `Alarm`。
- 先用本项目的视频回放与评测集验证它在目标工序上的收益，再决定是否采用其训练/推理微服务。
- 保留本项目自己的 SOP 版本、执行实例、规则判定、人工复核、证据追溯和审计。

**首期不直接引入的原因：**

- 其完整训练流程涉及标注、生成训练 QA、VLM/时序模型训练和部署；如果当前还没有稳定的工序视频与标注，直接接入会增加环境和模型验证成本。
- 它的模型能力不等于业务流程引擎；工位归属、执行实例识别、超时规则、告警确认和审计仍然需要平台自己负责。

### 3.2 NVIDIA DeepStream：视频推理运行时的可选高性能后端

项目：[`NVIDIA/DeepStream`](https://github.com/NVIDIA/DeepStream)；官方架构说明：[DeepStream Reference Application](https://docs.nvidia.com/deepstream/text/DS_ref_app_deepstream)

DeepStream 的核心价值是基于 GStreamer 的多路视频处理、GPU 解码、批量推理、跟踪和流处理组件。它不是 SOP 业务层，也不应成为领域模型的依赖。

**吸收方式：**

- 首期 `Video Runtime` 先通过文件/RTSP/OpenCV/厂商 SDK Adapter 实现统一接口。
- 同时定义 `InferenceBackend` 接口；当多路视频的吞吐、GPU 利用率或解码成本成为瓶颈时，增加 `DeepStreamBackend`，不改 SOP 引擎。
- DeepStream 的 `nvstreammux`、`nvinfer`、`nvtracker` 等概念只留在运行时实现内部，不泄漏到 API/领域模型。
- 对 NVIDIA GPU 目标环境做独立性能基准；没有 NVIDIA GPU 或相机 SDK 与 DeepStream 管线不兼容时，保留普通 Python Runtime。

### 3.3 Osprey：可作为 DeepStream 集成的加速器，但要先做兼容性验证

项目：[`Ocel-Labs/Osprey`](https://github.com/Ocel-Labs/Osprey)

Osprey 是基于 NVIDIA DeepStream 8.0 的动态多路视频分析库，提供运行时增加/移除 RTSP/文件流、推理与跟踪管线，并通过独立进程与 IPC 分离视频处理和应用逻辑。它能减少直接处理 GStreamer/DeepStream 细节的工作，但会带入其支持的 DeepStream/CUDA/驱动/模型解析器约束。

**吸收方式：**

- 若现场明确使用 NVIDIA GPU + RTSP 视频源，优先做一个小型 Spike，验证 Osprey 是否能替代我们自写的多流采集/推理运行时。
- 将 Osprey 包在 `VideoRuntimeAdapter` 后面；平台只接收标准事件、健康状态和证据引用。
- Osprey 的 RTSP 输出可用于调试/预览，但不能把它的输出流当作审计证据的唯一来源。
- 由于 Osprey README 所描述的环境基于 DeepStream 8.0，必须单独锁定并验证 OS、驱动、CUDA、TensorRT、Python、模型解析器版本；不可与其他 DeepStream 版本混装。
- 若相机主要使用 USB3 Vision/GigE Vision 厂商 SDK，而不是 RTSP，必须先验证源接入方式，不假设 Osprey 可以直接管理所有工业相机。

### 3.4 组合决策

| 项目/组件 | 在本系统中的定位 | PoC 是否必须 | 允许影响的边界 |
|---|---|---:|---|
| SOP Monitoring Blueprints | 时序 SOP 模型/训练流程参考，未来算法适配 | 否 | `TemporalRecognizer` 适配层 |
| DeepStream | 可替换的视频解码、批量推理、跟踪后端 | 否 | `Video Runtime` 内部 |
| Osprey | DeepStream 多路流接入的候选封装 | 否；先做 Spike | `VideoRuntimeAdapter` |
| FastAPI | 平台业务 API | 是 | 应用层，不负责视频长循环 |
| PostgreSQL | 业务事实主库 | 是 | 所有持久化领域数据 |
| React + TypeScript | Web 控制台 | 是 | UI 层，不承载业务判定 |

**关键结论：** 不需要在第一天把三个 NVIDIA 相关项目都装上。先把领域模型、事件契约和评测方式固定，再以实测结果决定运行时选型。开源项目的吸收应表现为可替换的 Adapter，而不是把外部项目的内部类型扩散到整个代码库。

---

## 4. 具体模块架构与代码边界

建议采用单仓库，业务后端与 Video Runtime 可以共享契约包，但不共享数据库写入职责。

```text
ai-sop-platform/
├── apps/
│   ├── web/                         # React + TypeScript 前端
│   ├── api/                         # FastAPI 应用入口、依赖注入、路由
│   └── video_runtime/               # 独立视频/推理进程入口
├── packages/
│   └── contracts/                   # Pydantic 事件模型、枚举、schema 版本
├── backend/
│   ├── api/                         # REST/WS 路由，只做输入输出适配
│   ├── application/                 # 用例服务、事务边界、命令处理
│   ├── domain/
│   │   ├── stations/                # Station、Camera、绑定关系
│   │   ├── sop_definitions/         # SOP 草稿、版本、DSL 校验
│   │   ├── executions/              # SOPExecution、Step 状态迁移
│   │   ├── events/                  # 事件校验、去重、关联、路由
│   │   ├── alarms/                  # 告警生命周期、确认/关闭
│   │   ├── evidence/                # 证据元数据与访问策略
│   │   └── health/                  # 相机、Runtime、推理、平台健康
│   ├── infrastructure/
│   │   ├── db/                      # SQLAlchemy models、session、repositories
│   │   ├── outbox/                  # Outbox 写入与 dispatcher
│   │   ├── evidence_store/          # 本地文件/对象存储实现
│   │   ├── runtime_clients/         # Video Runtime HTTP client
│   │   └── auth/                    # 用户、角色、鉴权
│   └── migrations/                  # Alembic
├── runtime/
│   ├── sources/                     # FileSource、RTSPSource、VendorSDKSource
│   ├── sampling/                    # 抽帧、ROI、采样策略
│   ├── inference/                   # InferenceBackend 协议与实现
│   ├── recognition/                 # 检测、跟踪、时序识别器
│   ├── event_builder/               # 模型输出转标准事件
│   ├── evidence/                    # 关键帧/片段捕获与哈希
│   └── health/                      # 运行时心跳与指标
├── sop_dsl/                         # DSL schema、静态校验、示例
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── scenarios/
├── deploy/
│   ├── compose.yaml                 # 本地/PoC 服务
│   └── configs/
├── docs/
│   ├── adr/                         # Architecture Decision Records
│   └── runbooks/                    # 安装、排障、备份、恢复
└── pyproject.toml / package.json
```

**目录说明**：`apps/` 只是进程入口，业务代码在 `backend/`；若仓库已采用 `backend/` 包布局，可以省略 `apps/` 层，不影响模块边界。`runtime/` 是视频运行时的库与入口，不导入后端 ORM。目录树不是迁移指令，落地映射以 ADR-0001 与 `docs/implementation/README.md` 为准。

### 4.1 模块依赖规则

- `domain` 不依赖 FastAPI、SQLAlchemy、OpenCV、PyTorch、DeepStream 或 Osprey。
- `application` 可以依赖领域对象和抽象接口；负责用例编排与事务边界。
- `infrastructure` 实现数据库、文件存储、Runtime 客户端等接口。
- `api` 只负责 HTTP/WS 协议、认证、请求校验和响应序列化。
- `runtime` 不导入后端 ORM，不直写 PostgreSQL 业务表。
- `packages/contracts` 只放跨进程稳定契约，不放 ORM 模型或业务服务。
- 外部开源项目只能通过 Adapter 接入；禁止把 `NvDs*`、Osprey 内部对象或模型框架对象作为业务 API 的返回类型。

---

## 5. 核心领域模型与关系

### 5.1 实体关系

```text
Station ──< StationCameraBinding >── Camera
   │                                   │
   │                                   └──< CameraHealthEvent
   │
   ├──< SOPExecution >── SOPVersion >── SOPDefinition
   │          │                 │
   │          ├──< StepExecution │
   │          ├──< RoutedEvent   └──< SOPStepDefinition (DAG)
   │          ├──< Alarm
   │          └──< AuditRecord
   │
   └──< StationRuntimeState

VisionEvent ──< EventEvidence >── EvidenceAsset
OutboxMessage ──> WebSocket/notification publisher
```

**说明**：`StationRuntimeState` 是**可重建的读模型投影**（用于总览页和 `runtime-state` 接口），不是事实来源，不要求单独建表。步骤与事件的关联记录在 `step_executions.matched_event_ids`，不复用 `event_evidence_links`（后者只表达事件↔证据）。

### 5.2 必需的业务实体

- `Station`：物理工位或逻辑工作单元。
- `Camera`：视频源设备；不将相机品牌/SDK 类型写入领域逻辑。
- `StationCameraBinding`：相机与工位的绑定、视角角色、采样策略。
- `SOPDefinition`：工艺身份。
- `SOPVersion`：不可变的已发布工艺版本。
- `SOPStepDefinition`：某版本中的步骤节点及依赖关系。
- `SOPExecution`：一次真实工序执行，绑定固定 SOP 版本。
- `StepExecution`：该执行实例中某个步骤的状态与判定记录。
- `Observation`：模型或传感器的单次观测。
- `VisionEvent`：从一个或多个 Observation 汇总的标准化候选事件。
- `RoutedSOPEvent`：已确定工位/执行实例归属、允许进入 SOP 引擎的事件。
- `EvidenceAsset`：证据文件元数据、哈希、存储位置和可用状态。
- `Alarm`：工艺异常、视觉质量问题或系统故障。
- `OutboxMessage`：事务提交后需要异步投递的通知/事件。
- `AuditRecord`：SOP 发布、配置修改、告警确认等操作的审计记录。

### 5.3 核心关系与约束

- `SOPExecution` 必须固定引用一个不可变的 `SOPVersion`；发布新版本不能改变已开始的执行实例。
- 默认同一工位同一时刻只有一个活动执行实例；如现场存在并行工件，再通过明确的 `workpiece_id`/执行策略开放。
- 一个相机可被配置到一个主要工位；多工位共享视角必须显式建模，不允许隐式重复消费同一事件。
- Observation 可以没有 `execution_id`，但 RoutedSOPEvent 在进入 SOP 状态机前必须绑定有效执行实例。
- 事件归属不明确时进入隔离队列或 `NEEDS_REVIEW`，不得按相似名称、最近时间或模型猜测强行绑定。
- 所有状态变化必须有来源事件、规则/DSL 版本、发生时间、处理时间和审计记录。

---

## 6. SOP 定义：版本化受限 DSL + DAG 状态机

SOP 不是写死在 Python `if/else` 中，也不是允许任意代码的通用工作流。采用**版本化 JSON/YAML DSL + 静态校验 + 确定性状态机**。

### 6.1 DSL 示例

```yaml
schema_version: "1.0"
sop_key: "seat_assembly_basic"
version: 3
name: "座椅基础装配流程"
steps:
  - key: "place_frame"
    name: "放置骨架"
    type: "ACTION"
    required: true
    depends_on: []
    timeout_ms: 15000
    completion:
      mode: "EVENT_RULE"
      all:
        - event_type: "frame_placed"
          min_confidence: 0.90
          stable_for_ms: 500
    evidence:
      required: true
      kind: "keyframe"

  - key: "install_left_bolt"
    name: "安装左侧螺栓"
    type: "ACTION"
    required: true
    depends_on: ["place_frame"]
    timeout_ms: 20000
    completion:
      mode: "EVENT_RULE"
      all:
        - event_type: "left_bolt_installed"
          min_confidence: 0.92
    evidence:
      required: true
      kind: "keyframe"

  - key: "install_right_bolt"
    name: "安装右侧螺栓"
    type: "ACTION"
    required: true
    depends_on: ["place_frame"]
    timeout_ms: 20000
    completion:
      mode: "EVENT_RULE"
      all:
        - event_type: "right_bolt_installed"
          min_confidence: 0.92
    evidence:
      required: true
      kind: "keyframe"

  - key: "verify_both_bolts"
    name: "确认两侧螺栓完成"
    type: "CHECKPOINT"
    required: true
    depends_on: ["install_left_bolt", "install_right_bolt"]
    join_policy: "ALL_REQUIRED"
    completion:
      mode: "STATE_RULE"
      all_steps_completed: ["install_left_bolt", "install_right_bolt"]
```

**补全的 DSL 字段**：

- `required: false` 的可选步骤必须声明 `skip_if`；阶段 1 支持 `{all_steps_completed: [...]}` 与 `{event_type: "..."}` 两种。
- 可选失败规则：`failure: {event_type: "...", reason_code: "..."}`；未声明时 `FAILED` 只能由人工复核产生（A16）。
- `join_policy` 取 `"ALL_REQUIRED"` 或 `{"type": "ANY_OF_N", "n": N}`，`N` 不得大于依赖数（A3）。
- `evidence.kind` 取 `keyframe` | `clip` | `external`。
- 所有字段禁止任意表达式；未知字段拒绝（沿用 §6.2）。

### 6.2 DSL 静态校验必须包含

- `schema_version` 是否受支持；字段是否符合 JSON Schema/Pydantic schema。
- `key` 唯一性、依赖节点是否存在、DAG 是否有环。
- `depends_on` 是否存在不可能满足的依赖。
- 事件类型是否在已注册的事件目录中。
- 置信度、超时、稳定时间、证据类型是否在合法范围内。
- `skip_if`、`failure`、`join_policy`、`evidence.kind` 的字段与引用是否合法。
- 引用的事件类型是否在 `contracts` 的事件目录中注册（见 §7.5）。
- 不允许内嵌 Python/JavaScript、SQL、shell 或任意表达式。
- 发布时生成不可变版本快照与内容哈希；执行实例记录确切版本。

### 6.3 状态机职责

状态机接收已经校验和路由的 `RoutedSOPEvent`，执行确定性迁移并产出状态变化，不直接读取摄像头帧、不调用模型、不访问外部 API。

典型步骤状态：`PENDING`、`ACTIVE`、`COMPLETED`、`FAILED`、`SKIPPED`、`TIMED_OUT`、`NEEDS_REVIEW`。

典型执行状态：`CREATED`、`RUNNING`、`PAUSED`、`COMPLETED`、`ABORTED`、`NEEDS_REVIEW`。

- 并行分支通过 DAG 的 `depends_on` 和 `join_policy` 表达。
- 可选步骤只有在 DSL 明确声明且符合跳过条件时才能跳过。
- 低置信度、证据缺失、多相机冲突或执行实例归属不明，进入 `NEEDS_REVIEW`，而不是自动判 NG。
- 迟到事件按执行周期的开始/结束时间与配置的迟到窗口处理；已结束的执行实例不接受普通事件推进状态，除非走显式更正流程。

**精确定义（A12–A14）**：

- `TIMED_OUT` 对自动迁移是终态：迟到证据只能补充证据或进入 `NEEDS_REVIEW`，不得自动改回 `COMPLETED`。
- 超时时钟从步骤进入 `ACTIVE` 起算；`activated_at`、`deadline_at` 落库，由周期扫描任务推进，不使用进程内睡眠。暂停期间不计时，累计 `paused_ms`。
- 每次步骤或执行状态迁移后，必须重新评估所有下游 `STATE_RULE` 与汇合节点；只在收到事件时评估会导致 CHECKPOINT 永不完成。
- 汇合节点只有在所有依赖进入终态后才可判定；`ANY_OF_N` 未达到 `N` 时保持等待，不得提前解锁。
- 人工复核与人工跳过走显式命令，记录操作者、决定、理由与证据；复核不改变原始模型输出。

---

## 7. 视觉事件契约与执行实例关联

### 7.1 事件分层

```text
Frame / Sensor Signal
        ↓
Observation（原始观测）
        ↓ Event Builder
VisionEvent（候选事件，可能尚未绑定执行实例）
        ↓ Event Validator + Deduplicator + Execution Resolver
RoutedSOPEvent（已绑定工位和执行实例）
        ↓
SOP State Machine
        ↓
StepExecution / Alarm / Audit / Outbox
```

### 7.2 VisionEvent 示例

```json
{
  "schema_version": "1.0",
  "event_id": "0190f6e2-0f25-7b2a-9d23-52e1c00c0001",
  "event_type": "left_bolt_installed",
  "station_id": "station-01",
  "camera_id": "camera-left",
  "occurred_at": "2026-10-27T10:12:03.420Z",
  "emitted_at": "2026-10-27T10:12:03.510Z",
  "frame_seq": 18290,
  "confidence": 0.94,
  "model": {"name": "bolt-state-detector", "version": "2026-10-15"},
  "observation_ids": ["obs-001", "obs-002"],
  "evidence_refs": ["evidence-001"],
  "attributes": {"side": "left", "roi": "bolt_zone_left"}
}
```

### 7.3 ExecutionResolver 规则

1. 如果上游携带合法 `execution_id`，校验它是否属于该工位、是否处于可接收事件的状态、事件时间是否落在允许窗口内。
2. 若未携带 `execution_id`，根据工位当前活动执行实例和事件时间窗口进行确定性解析。
3. 若没有活动执行实例、存在多个候选实例、事件属于已结束周期，或时间戳不可信，事件进入隔离/复核，不允许猜测绑定。
4. 所有解析结果记录 resolver 规则版本、候选集和原因码，以便审计。
5. 隔离事件只能通过显式 `assign` 命令改绑（A9）：校验同工位、未终态、时间窗内，写审计记录与新的处理回执；任何情况下不得自动重绑。

### 7.4 幂等、重复和乱序

- `event_id` 是全局幂等键；重复到达不重复推进状态。
- 每个相机的 `frame_seq` 单调递增；同时保留设备时间与服务接收时间。
- 事件先按 `occurred_at`、执行实例和规则要求进行时序校验；不满足规则的迟到事件不直接覆盖新状态。
- 事件处理需要明确返回 `ACCEPTED`、`DUPLICATE`、`QUARANTINED`、`REJECTED` 等结果。
- 推理运行时网络中断时必须有重试/有限本地持久化策略；超过保留上限时上报事件丢失计数和健康告警。
- **处理结果持久化（A19）**：`vision_events` 以 `event_id` 唯一保存已接收事件；`event_processing_receipts` 以 `event_id` 唯一保存最终结果（`ACCEPTED`/`DUPLICATE`/`QUARANTINED`/`REJECTED`）、`execution_id`、`reason_code` 与尝试次数。二者职责不同，不能用回执代替事件存储，也不能用事件表代替处理结果。
- **时钟与排序（A24）**：同一相机以 `frame_seq` 为权威顺序；跨相机只做容差窗口匹配，不做严格全序。部署要求 NTP 同步，事件保留设备时间与服务接收时间两个字段。

### 7.5 事件目录与版本（A28）

- 事件类型在 `contracts/catalog` 注册，每个类型声明必需 `attributes` 的 schema 与版本。
- 兼容策略：只允许追加可选字段；破坏性变更提升 `schema_version`，并提供双发窗口与迁移说明。
- 未知事件类型不得静默落库；按 `REJECTED` 处理并留痕。
- 阶段 1 事件目录保持最小；阶段 2 完成视频数据评审后冻结步骤级事件集合，冻结后按版本演进。

---

## 8. 多相机事件关联与冲突处理

首版采用**规则驱动关联**，不做复杂的多视角几何重建。

1. 先根据 `station_id`、相机角色、事件类型和时间窗口筛选可关联事件。
2. 根据 SOP 规则定义哪些相机是主证据、辅助证据或必须同时满足的证据来源。
3. 不允许简单平均不同模型的 confidence。不同相机的置信度不一定经过校准，且观察角度、遮挡和模型能力不同。
4. 如果两台相机结论冲突，按规则优先级处理；没有明确优先级时产生 `NEEDS_REVIEW`，保留所有证据与来源。
5. 记录关联规则版本、输入事件 ID、最终结果和原因码。
6. 后续如确有需要，再引入跨相机目标跟踪、标定或几何融合；它属于单独的算法能力，不应与 SOP 状态机耦合。

**可执行定义（A15）**：

- **冲突**：同一 `correlation_key` 在配置时间窗内出现互相排斥的结论（例如一侧报告已安装、另一侧报告缺失或反向状态），或必需视角报告证据不足。
- **correlation_key**：由事件类型定义的稳定业务键（如 `workpiece_id + side + part_id`）生成；无法生成时不得跨事件去重。
- **独立证据**：不同相机、不同观测时间、且不共享同一模型输出的证据。同一相机的多帧不算独立证据。
- 缺任何一条判定依据时进入 `NEEDS_REVIEW`，不得用置信度平均、投票或简单多数凑出结论。

---

## 9. 事务一致性：数据库、证据与通知

### 9.1 数据库事务 + Outbox

一次业务状态迁移的数据库事务中，至少写入：

- 新的 `StepExecution` / `SOPExecution` 状态；
- 对应 `Alarm`（若有）；
- `AuditRecord`；
- `OutboxMessage`（待推送的状态变化/告警通知）。

事务提交后由 `OutboxDispatcher` 异步发布 WebSocket 通知或外部通知。通知失败可以重试；前端断线重连后通过 REST 查询最新快照，不依赖 WebSocket 恰好在线。

### 9.2 证据文件一致性

文件与 PostgreSQL 无法天然组成单一原子事务，因此采用显式证据生命周期：

1. 写入临时文件；
2. 计算 SHA-256、尺寸、时间戳、相机、事件关联信息；
3. 原子移动到最终存储位置或完成对象存储上传；
4. 在数据库创建 `EvidenceAsset` 元数据，初始状态为 `PENDING_VERIFY`；
5. 校验文件存在、哈希匹配后标记 `AVAILABLE`；
6. 状态迁移只引用满足证据策略的证据；失败则进入待重试/复核，并由定期对账任务修复孤儿文件或缺失文件。

**跨进程交接（A10）**：阶段 1 的 runtime 与 backend 同机部署，runtime 将关键帧写入共享 `EVIDENCE_DIR/tmp/{event_id}.*`，事件只携带存储键；backend 负责校验、哈希、原子移动与 `evidence_assets` 生命周期，runtime 不建证据记录、不决定证据是否 `AVAILABLE`。runtime 分离部署时改为上传接口，事件的 `evidence_refs` 契约不变。

### 9.3 证据访问

证据接口必须做鉴权与授权，不能仅凭猜测 URL 访问。下载/预览时检查用户角色、工位权限和证据保留状态。敏感视频不得出现在普通应用日志中。

---

## 10. 数据库设计基线

首版建议使用 PostgreSQL + SQLAlchemy 2.x + Alembic。数据库结构至少覆盖以下表（实际字段在迁移中明确，不把 JSONB 当成所有数据的替代品）。

| 表 | 作用 | 关键约束 |
|---|---|---|
| `stations` | 工位主数据 | `code` 唯一 |
| `cameras` | 相机/视频源配置 | 敏感配置不明文回传 |
| `station_camera_bindings` | 工位相机关系 | 绑定有效期/角色明确 |
| `sop_definitions` | SOP 身份 | `key` 唯一 |
| `sop_versions` | 不可变 SOP 版本 | `(sop_id, version)` 唯一、内容哈希 |
| `sop_step_definitions` | DAG 节点 | `(sop_version_id, step_key)` 唯一 |
| `sop_step_dependencies` | DAG 边 | 禁止重复边；发布前检测环 |
| `sop_executions` | 执行实例 | 固定 `sop_version_id`，执行时间完整 |
| `step_executions` | 步骤执行结果 | 同一执行实例/步骤的唯一性策略明确 |
| `observations` | 可选的原始观测索引 | 只保存有价值的观测，不存每帧全部张量 |
| `vision_events` | 标准事件 | `event_id` 唯一、schema 版本明确 |
| `event_processing_receipts` | 幂等/处理结果 | 防止重复事件重复生效 |
| `evidence_assets` | 证据元数据 | 哈希、状态、存储键、保留期 |
| `event_evidence_links` | 事件/证据关系 | 多对多关系 |
| `alarms` | 告警与确认流程 | 状态与严重级别分离 |
| `outbox_messages` | 可靠通知投递 | 未投递消息可重试 |
| `audit_records` | 操作审计 | 记录操作者、动作、对象、时间 |
| `runtime_health_events` | 运行时健康事件 | 与工艺告警分开 |

**补充字段与暂缓项（A5、A11、A20、A25）**：

- `step_executions.matched_event_ids`（JSONB 数组）：参与判定的 `event_id`，用于 `stable_for_ms` 重建与审计；不得只存聚合分数。
- `cameras.runtime_id`：指定负责该相机的运行时实例；无 runtime 时相机启停返回 503 并产生设备告警。
- `alarms` 增加 `first_seen_at`、`last_seen_at`、`occurrence_count`，用于重复告警归并。
- `event_processing_receipts(event_id)` 唯一，保存最终处理结果与原因码。
- `StationRuntimeState` 是投影，不建表。
- 阶段 1 允许暂缓建 `observations`、`event_evidence_links`、`runtime_health_events`、`sop_step_dependencies` 四张表：事件已携带 `evidence_refs`，依赖可由 `sop_step_definitions.depends_on` 承载。暂缓不等于删除，阶段 2 需要时按本表补迁移。

**不要把每一帧都写进 PostgreSQL。** 高频帧和推理中间数据走内存/运行时队列；数据库保存事件、步骤结果、必要的 Observation 索引、证据元数据和健康状态。

### 10.1 索引与并发

- `vision_events(event_id)` 唯一索引。
- `event_processing_receipts(event_id)` 唯一索引；`step_executions(execution_id, step_key)` 唯一约束。
- `sop_executions(station_id, status)` 支持查找活动执行实例。
- `step_executions(execution_id, step_key)` 唯一约束或等效幂等策略。
- `alarms(status, severity, created_at)` 支持告警中心查询。
- `evidence_assets(sha256)` 可用于文件去重/完整性检查。
- SOP 状态迁移通过事务、行锁或乐观锁版本号防止并发事件覆盖状态。

---

## 11. API 与实时通信设计

REST API 的 Pydantic 模型是 API schema 来源；FastAPI 生成 OpenAPI，前端类型由 OpenAPI 生成工具生成。禁止前端手工维护一套长期漂移的 API 类型。

### 11.1 首期 API 资源

API 不引入版本段，下列路径均相对于 API 根。

```text
GET/POST /stations
GET      /stations/{station_id}
GET      /stations/{station_id}/runtime-state

GET/POST /cameras
PATCH    /cameras/{camera_id}
POST     /cameras/{camera_id}/start
POST     /cameras/{camera_id}/stop
GET      /cameras/{camera_id}/health

GET/POST /sops
GET/PATCH /sops/{sop_id}                      # 仅草稿可改（A8）
POST     /sops/{sop_id}/validate
POST     /sops/{sop_id}/publish
GET      /sops/{sop_id}/versions

POST     /stations/{station_id}/executions    # body: {sop_version_id, workpiece_id?}
GET      /executions?station_id=&status=&from=&to=
GET      /executions/{execution_id}
POST     /executions/{execution_id}/pause
POST     /executions/{execution_id}/resume
POST     /executions/{execution_id}/abort
GET      /executions/{execution_id}/timeline
POST     /executions/{execution_id}/steps/{step_key}/review
POST     /executions/{execution_id}/steps/{step_key}/skip

GET      /alarms
POST     /alarms/{alarm_id}/acknowledge
POST     /alarms/{alarm_id}/resolve
GET      /evidence/{evidence_id}
GET      /health/summary

POST     /events                              # 运行时投递，幂等键 = event_id
GET      /events?status=QUARANTINED
POST     /events/{event_id}/assign            # 显式改绑（A9）

POST     /runtimes/register
POST     /runtimes/{runtime_id}/heartbeat
GET      /runtimes
```

**请求语义（A7、A20、A21、A22）**：

- 创建执行实例必带 `sop_version_id`；阶段 1 不建工位→SOP 绑定表。工位已有活动实例时返回 409，必须显式中止或完成。
- 相机启停通过 Runtime 转发；未注册 runtime 时返回 503，并产生 `DEVICE_HEALTH` 告警。
- `review` 与 `skip` 必须带操作者、决定、理由与证据引用；均写审计记录。

API 的创建/发布/确认等写操作必须做授权、审计和输入校验。资源状态不应通过任意 PATCH 直接修改；需要显式命令端点。

### 11.2 WebSocket

建议使用单一版本化事件信封：

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

WebSocket 只推送状态变化、告警、运行时健康和必要的执行进度，不推送连续视频帧。客户端断线后重新连接并通过 REST 拉取快照；必要时用 `message_id`/游标补齐增量。

**安全要求（A23）**：WebSocket 必须鉴权，并按角色与工位过滤订阅；服务间凭据不得用于浏览器连接。Runtime→API 的写入接口使用独立 service credential，权限仅限事件投递、证据写入与心跳。

### 11.3 视频预览与证据回放分开

- **实时预览**：使用浏览器可播放的流方案，首期可根据相机能力选择 MJPEG/WebRTC/RTSP 网关；不要把预览流当作证据存档。
- **证据回放**：通过受控证据 API 获取图片或短视频片段，带访问授权、哈希和保留策略。
- 不预先承诺某一种视频协议，必须在目标浏览器、相机输出、网络和延迟要求明确后选定。

---

## 12. Video Runtime 与推理后端设计

### 12.1 运行时内部管线

```text
SourceAdapter
   ↓
FrameBuffer（有界队列，背压策略明确）
   ↓
FrameSampler（每相机/工位采样率、ROI、触发策略）
   ↓
InferenceBackend
   ├── PythonBackend（PoC 默认）
   ├── ONNXRuntimeBackend（按模型与硬件评估）
   └── DeepStreamBackend / OspreyAdapter（经基准验证后）
   ↓
Recognizer（检测/分类/跟踪/时序模型）
   ↓
EventBuilder（标准化事件、模型版本、时间戳）
   ├── EvidenceCapture
   └── EventPublisher → API
```

### 12.2 抽象接口（概念层）

```python
class VideoSource(Protocol):
    def start(self) -> None: ...
    def read(self) -> Frame | None: ...
    def health(self) -> SourceHealth: ...
    def stop(self) -> None: ...

class InferenceBackend(Protocol):
    def load(self, model_config: ModelConfig) -> None: ...
    def infer(self, batch: list[Frame]) -> list[RawInferenceResult]: ...
    def health(self) -> RuntimeHealth: ...
    def close(self) -> None: ...

class EventPublisher(Protocol):
    def publish(self, event: VisionEvent) -> PublishResult: ...
```

这只是接口边界示意，不要求逐字照搬。实现时需考虑 async/thread 模型、帧内存生命周期、队列满时的丢帧/降采样策略和关闭过程。

### 12.3 首期策略

- 先支持文件回放，再接入一种真实相机/RTSP 源。
- 抽帧与推理频率按工位和模型配置，不能默认每帧运行全部模型。
- 帧队列必须有界，不能在推理变慢时无限堆积旧帧。
- 事件包含模型名称/版本、阈值配置版本和来源帧/证据引用。
- `InferenceBackend` 是架构接口；首期可以只实现一个 Python 后端，不为尚未测量的性能问题预写多个完整后端。
- DeepStream/Osprey 通过独立实验分支验证，不允许为了接入它们重写 SOP 领域逻辑。

---

## 13. 健康状态、告警与人工复核

### 13.1 健康状态

统一健康状态枚举：`UNKNOWN`、`STARTING`、`HEALTHY`、`DEGRADED`、`UNAVAILABLE`、`MISCONFIGURED`、`STOPPED`。

相机健康、Runtime 健康、模型推理健康、数据库/平台健康分开记录；不能把相机断流误判成工艺漏步。

### 13.2 告警分类

- `PROCESS_COMPLIANCE`：漏步、错序、超时、步骤不合规。
- `VISION_QUALITY`：低置信度、遮挡、图像质量差、多相机冲突。
- `DEVICE_HEALTH`：相机断流、曝光/帧率异常、设备不可用。
- `INFERENCE_HEALTH`：模型加载失败、推理超时、GPU/Runtime 异常。
- `PLATFORM_HEALTH`：数据库、API、Outbox 或存储故障。
- `CONFIGURATION`：无有效 SOP、配置不兼容、模型版本未配置。

告警字段至少包含 `category`、`severity`、`status`、`station_id`、`execution_id`（可空）、`source_event_id`、`reason_code`、`created_at`、`acknowledged_by`、`resolved_at`。

### 13.3 人工复核不是异常兜底垃圾桶

以下情况应有明确原因码进入 `NEEDS_REVIEW`：执行实例不明确、事件低置信度、相机冲突、证据丢失、事件迟到、模型/规则版本不匹配。人工确认必须记录操作者、决定、理由和证据；复核结果不能抹去原始模型输出。

**最小 `reason_code` 枚举（A17）**：`EXECUTION_AMBIGUOUS`、`LOW_CONFIDENCE`、`EVIDENCE_MISSING`、`CAMERA_CONFLICT`、`LATE_EVENT`、`MODEL_VERSION_MISMATCH`、`RULE_VERSION_MISMATCH`、`MANUAL_SKIP`、`TIMEOUT`、`UNEXPECTED_STEP`、`OUT_OF_ORDER`。新增原因码必须同时更新契约枚举、前端筛选与测试；禁止使用自由文本代替原因码。

---

## 14. 前端页面与状态组织

首期前端只实现业务闭环必需的页面，不先做大型可视化配置器。

1. **工位总览**：工位状态、活动执行、未处理告警、相机/Runtime 健康。
2. **工位监控页**：实时预览、当前 SOP 步骤、最近事件、证据入口、健康状态。
3. **SOP 管理页**：草稿编辑、DAG 可视化/步骤依赖、静态校验、发布与版本历史。
4. **执行历史页**：执行时间线、每步结果、来源事件、模型/规则版本、证据回放。
5. **告警中心**：分类、严重程度、确认/关闭、关联工位和证据。
6. **系统配置页**：相机源、绑定关系、模型配置、采样策略、运行时状态。

前端不得自行推导最终 SOP 结论。服务端是状态权威；WebSocket 用于及时刷新，REST 用于初始加载、重连恢复和历史查询。

---

## 15. 部署架构与环境策略

### 15.1 PoC 部署

```text
开发机/实验台
├── web（Vite 开发服务器；部署时可静态托管）
├── api（FastAPI）
├── video-runtime（Python 独立进程）
├── postgres（Docker Compose）
└── evidence/（本地持久化目录）
```

- Docker Compose 用于管理 PostgreSQL、API、Web 等通用服务。
- 若工业相机 SDK、GPU、DeepStream 与容器兼容性复杂，Video Runtime 可先在宿主机运行；不强迫所有东西容器化。
- 所有容器/进程通过健康检查与 readiness 状态暴露是否可服务。
- 数据库、证据目录必须使用持久化卷；禁止把重要证据只写入容器可写层。

### 15.2 生产线扩展原则

- 先按工位/相机组划分 Runtime 实例，再按测得的 GPU/CPU/网络负载调整部署。
- 允许一个 API 服务管理多个 Runtime 实例；Runtime 注册 `runtime_id`、负责的相机列表、版本与心跳。
- 任何 Runtime 重启后都必须重新声明相机状态，不能把重启前的内存状态当作事实。
- 生产部署补充备份恢复、时间同步、日志轮转、证据存储容量告警、权限管理和升级回滚流程。

### 15.3 认证与权限

基础角色：`VIEWER`、`OPERATOR`、`ENGINEER`、`ADMIN`。

- `VIEWER`：查看监控、历史和授权范围内的证据。
- `OPERATOR`：确认/关闭允许操作的告警、执行规定的暂停/恢复操作。
- `ENGINEER`：管理相机、模型配置、SOP 草稿并发起发布。
- `ADMIN`：用户/角色、全局配置和高风险管理操作。

开发环境可通过显式配置关闭认证；生产环境没有认证配置时必须启动失败。证据文件不能绕过 API 权限直接暴露为公开目录。

**服务间认证（A23）**：Video Runtime 投递事件、写入证据、发送心跳使用独立 service credential（受限 token 或 mTLS），不得复用用户角色。开发模式可关闭，但生产缺少该配置时必须启动失败。

---

## 16. 数据保留、审计和可观测性

以下是 PoC 初始值，必须在生产试点前与现场确认：

| 数据 | PoC 默认保留 | 说明 |
|---|---:|---|
| SOP 执行/步骤结果/审计 | 至少 180 天 | 业务追溯数据 |
| 告警与处理记录 | 180 天 | 需要按客户要求调整 |
| 证据关键帧 | 30 天 | 可按异常等级延长 |
| 告警前后短视频 | 默认关闭；开启后 7 天 | 需控制存储容量和隐私风险 |
| 原始连续视频 | 默认不持久化 | 由现有录像系统负责时不重复存储 |
| 应用/Runtime 日志 | 14 天 | 日志不得含凭据或完整敏感视频内容 |
| 高频原始 Observation | 不长期保留 | 仅保留调试/追溯所需子集 |

**保留锁与恢复（A27）**：被调查或锁定的证据可设置 legal hold，优先于保留清理；删除证据不得删除审计元数据。阶段 2 必须完成一次数据库 + 证据目录的备份恢复演练，不能把首次恢复留到生产上线。

必须提供基础指标：每路相机 FPS、采样 FPS、推理延迟、事件生成延迟、事件发送失败/重试数、丢帧数、Runtime 重启次数、数据库连接状态、Outbox 未投递数量、证据缺失数量、人工复核积压量。

日志要包含 `station_id`、`camera_id`、`execution_id`（若有）、`event_id`、`runtime_id` 和关联 trace/request ID，便于跨模块排障。

---

## 17. 测试与验收架构

### 17.1 必须有的测试层

- **Domain 单元测试**：SOP DAG、合法/非法状态迁移、超时、可选步骤、并行汇合。
- **Contract 测试**：VisionEvent、RoutedSOPEvent、WebSocket 消息 schema 版本与兼容性。
- **Repository/事务集成测试**：幂等、Outbox 原子写入、并发状态迁移、数据库回滚。
- **Runtime 测试**：文件视频回放、源断开/重连、帧队列背压、模型超时、事件发送失败。
- **端到端场景测试**：从视频/模拟事件到 SOP 结果、告警、证据和 UI 更新。
- **故障测试**：API 重启、Runtime 重启、数据库暂不可用、重复/乱序/迟到事件、证据写入中断。

### 17.2 PoC 验收标准

1. 使用固定样例视频可以重复运行同一 SOP 场景，得到可解释且可复现的步骤时间线。
2. 重复投递同一个 `event_id` 不会重复完成步骤或重复产生告警。
3. 事件无法关联执行实例时不会错误推进 SOP。
4. 每个完成/异常步骤都能查看来源事件、规则版本和证据状态。
5. Runtime/相机故障显示为系统健康告警，不伪装成工艺违规。
6. API/前端类型由 OpenAPI 生成链保持同步；CI 检查 schema 生成文件是否过期。
7. 通过模拟相机和事件完成闭环后，再进入真实相机验证。

**量化门槛（A26，本地 PoC 目标）**：

- 10,000 条脚本事件回放：0 丢失、0 重复状态迁移；
- 同一 `event_id` 重放 10 次：恰好 1 次状态迁移、1 条告警；
- 事件 `POST` → 数据库提交 p95 ≤ 100 ms（本地、单工位）；
- 状态提交 → WebSocket 推送 p95 ≤ 300 ms；
- 断线重连后 2 秒内通过 REST 恢复权威状态；
- 无歧义脚本场景的隔离率必须为 0；有歧义场景必须 100% 进入隔离。

这些是平台闭环门槛，不代表视觉模型精度。

---

## 18. 推荐实施顺序

### 阶段 0：现场假设与接口验证

确认相机类型（RTSP、USB3 Vision、GigE Vision、厂商 SDK）、GPU/OS、工位数量、实时预览要求、SOP 是否需要产品身份识别、证据保存要求。此阶段只做最小技术验证，不提前铺开功能。

### 阶段 1：业务闭环骨架

实现 PostgreSQL/Alembic、Station/Camera/SOPVersion/SOPExecution 基础实体、SOP DSL 静态校验、确定性状态机、模拟事件 API、Outbox、最小前端工位状态页。先不接真实视觉模型。

**交付拆分（A25）**：阶段 1 分 1A / 1B。

- **1A**：线性 DAG、超时、人工复核、事件闭环、最小 UI；对应 `step_executions` 等核心表。
- **1B**：并行分支、`ALL_REQUIRED` / `ANY_OF_N` 汇合、可选步骤、多相机规则关联。
- 1B 不改变 1A 的契约，可以在 1A 端到端演示之后交付，但不得跳过；跳过会把并行、可选、多相机这三项核心能力永久推迟。
- 阶段 1 允许暂缓建 §10 说明中的四张表，先用事件内 `evidence_refs` 与步骤内 `depends_on` 承载。

### 阶段 2：视频回放与事件生成

实现 FileSource、抽帧、一个最小识别器或模拟识别器、EventBuilder、证据关键帧、Runtime 健康状态；让视频回放真正驱动 SOP 状态变化。

### 阶段 3：接入一台真实相机

实现对应 Source Adapter，验证断线重连、时间戳、帧率、曝光、运行稳定性和证据质量。再增加第二台相机并验证事件关联与冲突处理。

### 阶段 4：评估 DeepStream/Osprey/SOP Blueprints

分成独立 Spike，不阻塞主干业务系统：

- Spike A：同一段视频、同一模型，在 Python Runtime 与 DeepStream/Osprey 下比较吞吐、延迟、GPU 占用、部署复杂度。
- Spike B：使用 SOP Monitoring Blueprints 评估目标工序的动作分段/步骤识别效果、数据标注成本和训练成本。
- 只有达到预先设定的收益门槛，才将其实现纳入正式部署路径。

### 阶段 5：多工位试点

增加工位隔离、相机批量配置、执行实例自动启动/结束规则、告警复核、权限、备份恢复、日志和容量监控。用真实场景验收后再决定是否拆服务。

---

## 19. 架构风险与明确的决策门槛

| 风险/不确定性 | 当前处理 | 何时重新决策 |
|---|---|---|
| 相机 SDK 无法直接容器化 | Runtime 可宿主机部署 | 现场确定相机品牌/SDK 后 |
| 多路推理吞吐不足 | 先基准测试，再选 DeepStream/Osprey | 明确相机数、分辨率、FPS、GPU 后 |
| SOP 模型数据不足 | 先模拟事件与固定视频评测 | 有代表性工序视频与标注后 |
| 执行实例自动关联不可靠 | 歧义隔离/人工确认 | 产品身份识别/PLC 信号接入后 |
| 多相机结果冲突 | 规则优先级 + NEEDS_REVIEW | 有相机标定与融合需求后 |
| 实时视频浏览器兼容性 | 预览协议独立于证据存储 | 目标浏览器/网络确定后 |
| 数据量增长 | 不保存每帧中间数据，按保留期清理 | 试点测得事件量/证据量后 |

---

## 20. AI Coding Agent 的工作协议

这部分是实现约束，但它服务于前面定义的真实架构，不替代架构设计。

每个编码任务按以下顺序执行：

1. 先阅读本文件、相关 ADR、现有代码和测试；先报告计划改动的模块及其边界。
2. 把任务拆成可验证的小改动；不要一次性重写整套项目。
3. 新增领域规则前先写测试；外部模型输出必须经过契约校验，不能直接写数据库。
4. 修改 API schema 后重新生成 OpenAPI/前端类型，并检查差异。
5. 修改数据库结构必须新增 Alembic migration；不手工修改已应用迁移。
6. 引入开源依赖前检查许可证、版本、操作系统/GPU/驱动约束、维护状态和模型权重许可。
7. 每次完成运行相关单测、集成测试、lint 和类型检查；只报告实际执行的命令和结果。
8. 如果任务要求跨越模块边界或改变领域模型，先提出 ADR，不得默默改变架构。

### 20.1 ADR 触发条件

以下情况必须新增或更新 `docs/adr/`：

- 引入/替换 DeepStream、Osprey 或 SOP Monitoring Blueprints 的正式部署路径；
- 将模块化单体拆为独立业务微服务；
- 引入消息中间件、Redis、任务队列或分布式部署；
- 改变 SOP DSL、事件契约或执行实例关联规则；
- 改变数据库主数据模型或证据保留策略；
- 改变身份认证、证据访问控制或生产部署安全边界。

---

## 21. 尚需现场确认的事项

这些是需要用户/现场提供事实的输入，不应由 AI Coding Agent 自行假设：

1. 目标相机是 RTSP 网络相机，还是 USB3 Vision/GigE Vision 工业相机及厂商 SDK？
2. 推理主机是否有 NVIDIA GPU？型号、显存、OS/驱动是什么？
3. PoC 预计几路相机、分辨率、帧率与最大允许延迟？
4. SOP 执行实例如何开始/结束：人工按钮、条码/工件 ID、PLC 信号，还是视觉自动识别？
5. 实时预览的可接受延迟与目标浏览器是什么？
6. 异常证据需要保存图片还是短视频？现场要求保存多久？
7. 目标工序是否已有视频、动作标注或可用于评测的 OK/NG 样本？
8. 工位与 SOP 的绑定方式：执行创建时指定版本，还是工位维护默认版本？
9. 可选步骤的跳过语义由谁判定：超时跳过、分支完成跳过，还是只能人工跳过？
10. Video Runtime 与后端是否同机部署？这决定证据交接用共享目录还是上传接口。
11. 跨相机时间同步是否有 NTP/现场时钟约束？

---

## 22. 最终架构基线

1. **业务核心自有**：SOP 版本、执行实例、状态迁移、事件关联、告警、证据索引、权限和审计由本项目负责。
2. **推理能力可替换**：普通 Python Runtime 是 PoC 起点；DeepStream/Osprey 是性能/多流接入候选；SOP Monitoring Blueprints 是时序 SOP 算法候选。
3. **跨进程只传标准契约**：外部项目的内部对象不能泄漏进业务领域层。
4. **数据库是业务事实来源**：状态变化和 Outbox 同事务；证据采用显式生命周期与对账机制。
5. **SOP 是版本化 DAG**：发布前静态校验，执行实例固定版本，状态机确定性执行，歧义进入人工复核。
6. **先验证再复杂化**：先用视频回放/模拟事件形成闭环，再接真实相机，再评估高性能推理栈；所有扩展都由测量结果驱动。

这套设计的目标不是提前预测所有未来需求，而是让未来替换模型、相机 SDK 或推理运行时，不需要重写 SOP 业务核心。

---

## 23. 修订记录

本文只保留当前有效的设计。评审发现的矛盾、缺失与不可实现项及逐条处理见 `docs/adr/0001-architecture-baseline-review.md`，不在正文重复。
