# 工业 AI-SOP 多工位视觉监控平台：架构设计与 AI Agent 编程约束

> 文档版本：1.1（校订标注，2026-10-27）  
> 状态：**约束参考**（不再是架构基线）。架构以 `AI_SOP_Platform_Architecture_v2.0.md` 为准。  
> 适用阶段：实验台 PoC → 多工位试点 → 生产线部署  
> 目标读者：AI Coding Agent、系统架构师、后端/前端/视觉算法开发者
>
> **已被架构基线取代的条目**（其余条款继续作为约束参考有效）：
> - §4.5 `next` 与 `step_type`（`PARALLEL_GROUP`/`OPTIONAL`）冗余 → 以 `depends_on` + `join_policy` + `required`/`skip_if` 为准；
> - §4.6 `current_step_key` → 不落库，活动步骤由步骤结果派生；
> - §6.4.1 “进入 `IN_PROGRESS` 需开始证据” → 允许隐式激活与原子完成；
> - §6.4.2 “首版不支持并行” → 阶段 1B 支持；
> - §10 目录树 → 以基线 §4 与 `docs/implementation/README.md` 的映射为准。
>
> 缺陷编号与理由见 `docs/adr/0001-architecture-baseline-review.md`（A1–A4、A25）。

---

## 0. 给 AI Agent 的最高优先级指令

本文件是本项目的**顶层架构事实来源**。实现功能前，必须先阅读并遵守本文件。

1. 不得擅自改变本文确定的技术栈、模块边界、领域模型、事件契约或状态机职责。
2. 不得因为某个开源项目采用了不同架构，就把其目录、依赖和业务设计整体搬入本项目。
3. 不得为 PoC 创建与未来正式系统无关的临时架构。PoC 可以减少功能，但必须使用相同的核心领域模型和接口。
4. 不得在未说明影响、迁移成本、替代方案和测试计划的情况下修改架构基线。
5. 不得为了“提前扩展”引入微服务集群、Kafka、Redis、Kubernetes、向量数据库或复杂 Agent 框架。
6. 不得把模型输出直接当作 SOP 合格结论；视觉识别、事件解释、SOP 状态迁移必须分层。
7. 不得让前端、相机适配器或推理代码直接修改 SOP 状态或绕过业务服务写数据库。
8. 任何不确定的业务规则必须记录为 `OPEN QUESTION` 并向用户确认，不得自行假设后硬编码。
9. 实现前先检查仓库现状、依赖版本、测试与已有约定；不得盲目覆盖文件或重建项目。
10. 每个开发任务完成后，运行相关测试、类型检查、lint，并汇报实际执行结果；不得声称运行过未执行的检查。

若用户明确要求变更架构，先更新本文件及相关 ADR，再实施代码变更。

---

## 1. 项目目标与非目标

### 1.1 项目目标

构建一套可逐步落地的工业视觉 AI-SOP 监控平台，用摄像头持续观察装配/生产工位，识别可视觉验证的操作和工件状态，并根据工艺规则判断步骤完成、漏步、错序、超时和异常。

系统必须支持：

- 从本地视频回放开始开发，再接入真实相机。
- 从单工位单相机扩展到多工位、多相机。
- 不同工位配置不同 SOP；一个工位可以关联多台相机。
- 不同工位可以使用不同的模型、采样频率和识别策略。
- 模型和相机厂商可替换，尽量不影响 SOP 领域逻辑。
- 保存步骤执行记录、告警和必要的证据引用，支持历史追溯。
- 允许视觉模型与非视觉信号（例如工具控制器或 PLC 信号）共同作为工艺证据。
- 提供实时监控、配置、告警、历史查询的 Web 界面。

### 1.2 非目标（第一阶段不做）

- 不做通用视频管理平台或全厂级 VMS。
- 不假设所有 SOP 都能仅靠视觉可靠判断。
- 不在没有数据和评测的情况下承诺识别精度。
- 不把大语言模型作为每帧实时推理的默认路径。
- 不要求所有工位使用同一模型。
- 不在 PoC 阶段引入微服务集群、Kafka、Redis、Kubernetes。
- 不在首版实现复杂的多租户、计费、插件市场或通用工作流编辑器。
- 不直接控制危险设备或替代安全 PLC；AI-SOP 的告警不得作为唯一的机器安全联锁。

---

## 2. 架构决策摘要（必须遵守）

| 领域 | 基线决策 | 说明 |
|---|---|---|
| 前端 | React + TypeScript + Vite | Web UI；不把业务规则写在前端 |
| 应用后端 | Python + FastAPI + Pydantic | API、配置、用例协调、鉴权预留 |
| 核心业务 | 后端内的模块化单体 | 领域模块有清晰边界；首版不拆微服务 |
| 数据库 | PostgreSQL + SQLAlchemy 2.x + Alembic | 业务事实的持久化来源 |
| 视频/推理运行时 | 独立 Python 进程 | 与 API 生命周期隔离，允许独立重启 |
| 初期视频接入 | 文件/RTSP/OpenCV 或厂商 SDK 适配器 | 先实现一种最容易验证的输入，再扩展 |
| 推理引擎 | 模型无关的 Python Runtime 接口 | 先用 PyTorch/ONNX 等可落地方案；后续按测量结果接 DeepStream |
| 视觉输出 | 标准化 Observation / VisionEvent | 模型不得直接推进 SOP |
| SOP 逻辑 | 显式、可测试的状态机/规则引擎 | SOP 版本与每次执行实例绑定 |
| 进程间通信 | 版本化消息契约；首版可用本机 HTTP 或受控 IPC | 不将进程内事件总线当作跨进程协议 |
| 前后端实时更新 | WebSocket（仅推送状态变化/告警，不推送全量视频帧） | 视频流用独立视频路径或前端可播放源 |
| 部署 | Docker Compose 用于开发/试点；相机 SDK 允许宿主机部署 | 不要求 Kubernetes |
| 测试 | pytest + API/集成/场景测试；前端采用项目对应测试工具 | 测试是交付要求，不是可选项 |

### 2.1 为什么首版不强制 DeepStream / Osprey

DeepStream 是 NVIDIA GPU 视频分析运行时，不是业务架构。它的驱动、CUDA、TensorRT、DeepStream 和相机插件有明确兼容约束。先定义稳定的采集/推理契约，再用实际相机数量、分辨率、帧率、GPU、端到端延迟做基准测试，决定是否引入。

Osprey 可作为特定环境下的 DeepStream 多路视频适配候选，但不能成为业务层的必需依赖。USB3 Vision/GigE Vision 相机可能需要厂商 SDK，不能预设其可直接作为 RTSP 源接入。

### 2.2 开源项目的正确定位

- NVIDIA SOP Monitoring Blueprints：高级时序动作边界检测、VLM 合规分析和推理管线参考；按需学习/验证，不复制整个系统架构。
- NVIDIA DeepStream：GPU 视频处理和推理管线的可选后端。
- Osprey：DeepStream 多路视频运行时的可选适配候选。
- AI-SOP 等算法原型：用于比较检测、手部/工具特征、时序分类等思路，不作为项目的架构母版。
- 任何第三方代码在引入前，必须检查许可证、维护状态、运行环境、模型权重许可和部署成本。

---

## 3. 逻辑架构与数据流

```text
┌───────────────────────────────────────────────────────────────┐
│ React Web UI                                                   │
│ 工位总览 / 实时状态 / SOP 配置 / 告警 / 执行记录 / 证据回放     │
└───────────────────────┬───────────────────────────────────────┘
                        │ REST API + WebSocket
┌───────────────────────▼───────────────────────────────────────┐
│ FastAPI Application (模块化单体)                               │
│                                                               │
│ API → Application Services → Domain Modules → Repositories     │
│                                                               │
│ Station / Camera Config / SOP Definition / SOP Execution       │
│ Event Processing / Alarm / Evidence / Audit                    │
└───────────────────────┬───────────────────────────────────────┘
                        │ versioned message contract
┌───────────────────────▼───────────────────────────────────────┐
│ Inference Runtime (独立进程)                                   │
│ Camera Adapters → Frame Sampler → Model Pipeline → Event Builder│
│ 文件 / RTSP / 厂商 SDK        检测/跟踪/时序/状态变化           │
└───────────────────────────────────────────────────────────────┘
```

### 3.1 核心数据流

1. 设备适配器采集帧，为每帧附加 `camera_id`、采集时间戳和单调递增的帧序号。
2. Frame Sampler 按工位/模型配置选择需要推理的帧，避免无条件对所有帧运行所有模型。
3. 模型管线产生原始检测、跟踪、关键点、动作分数或状态变化。
4. Event Builder 将原始模型输出转换为版本化的标准化视觉事件。
5. 推理运行时将事件发送给应用后端；传输失败时按明确策略重试或记录失败，不可静默丢弃。
6. 后端校验事件、去重、检查时间顺序和关联关系，再交给对应工位的 `StationRuntime`。
7. SOP 状态机执行合法迁移并生成步骤状态变化、告警或待确认结果。
8. 业务服务将事件/状态/告警写入 PostgreSQL，并通过 WebSocket 通知前端。
9. 证据图像/视频片段使用独立证据存储接口；数据库保存引用和元数据，不将大视频二进制直接存入业务表。

### 3.2 关键隔离原则

- 相机采集线程/任务不得直接访问数据库。
- 模型代码不得直接写业务表。
- 视觉事件不得直接修改前端状态。
- SOP 状态机不得依赖 YOLO、PyTorch、OpenCV、DeepStream 等具体模型/视频库。
- 前端只通过 API 与 WebSocket 接触后端。
- 单台相机故障不能让所有工位停摆；单个工位的 SOP 异常不能污染其他工位状态。
- 事件处理应明确超时、重复、迟到、乱序和断线恢复行为。

---

## 4. 核心领域模型

至少实现以下实体；字段可在实现时细化，但不得合并其职责。

### 4.1 `Station`（工位）

代表物理或逻辑工作单元。

建议字段：`id`、`code`、`name`、`enabled`、`metadata`、`created_at`、`updated_at`。

### 4.2 `Camera`（相机）

代表视频采集设备或视频源。

建议字段：`id`、`code`、`source_type`、`source_config`、`enabled`、`health_status`、`created_at`、`updated_at`。

约束：凭据不得以明文返回 API 或写入日志。`source_config` 中的敏感字段应使用环境变量/秘密配置引用。

### 4.3 `StationCameraBinding`

将相机与工位关联，并允许定义相机视角/用途。

建议字段：`station_id`、`camera_id`、`role`、`enabled`、`sampling_policy`。

约束：一个工位允许多相机。相机是否能绑定多个工位必须由产品需求明确；初版默认同一时刻一个采集源只有一个主要归属，避免重复事件被多个工位消费。

### 4.4 `SOPDefinition` 与 `SOPVersion`

- `SOPDefinition` 表示工艺身份。
- `SOPVersion` 表示不可变的已发布工艺版本。
- 草稿可以修改；发布后的版本不可原地修改，只能发布新版本。
- 每个 `SOPExecution` 必须固定引用某个 `SOPVersion`。

### 4.5 `SOPStep`

建议字段：`id`、`sop_version_id`、`key`、`name`、`step_type`、`required`、`timeout_ms`、`completion_policy`、`evidence_requirements`、`transition_rules`。

不要将 `sequence` 作为唯一的流程模型。流程使用有向无环图（DAG）表达依赖关系；简单线性流程只是每一步依赖前一步的特例。`step_type` 首版限定为 `ACTION`、`PARALLEL_GROUP`、`OPTIONAL`、`CHECKPOINT`。循环/回退如无明确业务需求，首版不支持任意循环；返工应建模为显式分支或新的执行实例。

> **1.1 校订（作废）**：`PARALLEL_GROUP`、`OPTIONAL` 与 `required`、DAG 并行重复，架构基线收敛为 `ACTION` / `CHECKPOINT`；`next` 删除，统一使用 `depends_on`。见 ADR-0001 A2/A3。

`completion_policy` 必须使用第 6 节定义的受限 DSL，不得存储或执行任意 Python、JavaScript、SQL 或表达式脚本。

### 4.6 `SOPExecution`

代表某工位某次产品/工序周期的 SOP 执行实例。

建议字段：`id`、`station_id`、`sop_version_id`、`workpiece_id`（可空）、`status`、`current_step_key`、`started_at`、`finished_at`、`version`。

> **1.1 校订（作废）**：不落库单值 `current_step_key`；活动步骤由 `step_executions` 派生，否则与并行步骤矛盾。见 ADR-0001 A1。

状态建议：`IDLE`、`RUNNING`、`PAUSED`、`COMPLETED`、`ABORTED`、`NEEDS_REVIEW`。

同一工位是否允许多个并行执行实例取决于物理工艺；初版默认每个工位最多一个活动执行实例，但模型应使用独立的 `SOPExecution`，不能把当前步骤直接存成工位的全局字段。

### 4.7 `Observation`、`VisionEvent`、`SOPStepResult`、`Alarm`

- `Observation`：模型原始或中间观测，必要时保存，避免无价值地存储每一帧的所有中间张量。
- `VisionEvent`：从一个或多个观测归纳出的标准化候选事件。
- `SOPStepResult`：某个步骤的判定结果及证据引用。
- `Alarm`：已判定异常、待确认事项或系统故障告警。

必须区分：
1. 视觉观测（模型看到了什么）；
2. SOP 判定（工艺上是否完成/违规）；
3. 系统健康（相机/模型/通信是否故障）。

不得把三者合并成单一 `status` 字段。

---

## 5. 标准事件契约

所有跨模块/跨进程事件都必须有 schema 版本。

示例：

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "event_type": "screw_detected",
  "station_id": "station-01",
  "camera_id": "camera-01",
  "execution_id": "execution-uuid",
  "occurred_at": "2026-10-27T10:30:00+08:00",
  "emitted_at": "2026-10-27T10:30:00.120+08:00",
  "frame_sequence": 1842,
  "model": {
    "name": "part-detector",
    "version": "0.1.0"
  },
  "confidence": 0.96,
  "payload": {
    "object_class": "screw",
    "track_id": "track-17",
    "bbox_xyxy": [100, 120, 180, 220]
  },
  "evidence": {
    "image_ref": "evidence://..."
  }
}
```

### 5.1 契约约束

- `event_id` 全局唯一；重复投递时由后端幂等处理。
- 时间必须带时区；排序优先使用采集侧 `occurred_at`，同时保留服务端 `emitted_at`。
- `confidence` 是模型置信度，不等于 SOP 合格概率。
- `payload` 应按事件类型使用 Pydantic discriminated union 或等价的有类型 schema 校验，禁止把所有业务塞进无约束字典。
- 事件应携带模型名称和版本，便于回溯。
- 事件 schema 演进必须向后兼容；破坏性修改提升主版本并提供迁移/兼容策略。
- 原始 `Observation` 可以没有 `execution_id`；但任何交给 SOP 状态机的 `RoutedSOPEvent` 必须有非空 `execution_id`。事件关联未唯一确定时必须进入隔离队列/待人工确认，禁止直接推进 SOP。推理层不得自行猜测工件周期。
- 多相机融合时必须保留各来源的相机 ID、时间戳和证据引用。

---

## 6. SOP 状态机与业务规则

### 6.1 责任边界

SOP 引擎只依赖领域事件和 SOP 定义，不依赖模型库或视频库。

输入：
- 标准化 `VisionEvent`；
- 可选的工具控制器/PLC 等外部信号事件；
- 当前 `SOPExecution`；
- 不可变的 `SOPVersion`。

输出：
- 步骤状态变化；
- 执行实例状态变化；
- `Alarm` 或 `NeedsReview` 结果；
- 可审计的判定理由和证据引用。

### 6.2 步骤状态

至少支持：`PENDING`、`IN_PROGRESS`、`COMPLETED`、`SKIPPED`、`FAILED`、`NEEDS_REVIEW`。

### 6.3 必须明确的规则

- **漏步**：预期步骤尚未完成，但后续步骤事件出现。
- **错序**：事件对应的步骤与当前合法迁移不一致。
- **超时**：步骤超过配置的 `timeout_ms`，且超时策略启用。
- **重复操作**：同一动作重复出现；必须按 SOP 规则判定是否违规，不能一概视为异常。
- **证据不足**：置信度、观测持续时间、视角覆盖或外部信号不足时进入待确认，不得自动判为合格。
- **工位复位/新工件**：必须通过明确命令或可验证的周期边界开始新执行实例；不能因模型短暂漏检就自动清空状态。
- **事件迟到/乱序**：定义允许的时间窗口和处理策略；不能无条件回退已完成状态。
- **多相机冲突**：依据配置的证据优先级/融合规则处理；冲突无法消解时进入 `NEEDS_REVIEW`。
- **人工确认**：必须记录操作者、时间、理由和关联证据（身份认证能力未实现前可在开发环境使用测试用户，但接口须保留审计字段）。

### 6.4 SOP 规则 DSL（必须实现受限、版本化的声明式规则）

SOP 不使用任意代码作为配置。首版 DSL 采用 JSON/YAML 数据结构，经 Pydantic schema 校验后编译为内部不可变的规则对象。DSL 只表达可审计的状态迁移，不允许执行用户提供的代码。

最小定义示例：

```yaml
schema_version: "1.0"
sop_key: "assembly-demo"
version: 1
start_step: "place_part"
steps:
   - key: "place_part"
     type: "ACTION"
     required: true
     completion:
       all:
         - event_type: "part_placed"
           min_confidence: 0.90
           stable_for_ms: 300
     timeout_ms: 15000
     next: ["tighten_screw"]
   - key: "tighten_screw"
     type: "ACTION"
     required: true
     completion:
       all:
         - event_type: "screw_tightened_visual"
           min_confidence: 0.90
     timeout_ms: 20000
     next: ["final_check"]
   - key: "final_check"
     type: "CHECKPOINT"
     required: true
     completion:
       all:
         - event_type: "assembly_present"
           min_confidence: 0.95
     next: []
policy:
  on_unexpected_step_event: "RAISE_SEQUENCE_ALARM"
  on_ambiguous_evidence: "NEEDS_REVIEW"
  on_timeout: "RAISE_TIMEOUT_ALARM"
```

以上是说明性示例；实际 schema 应严格校验字段，禁止忽略未知字段。规则表达式只允许白名单操作符，例如 `all`、`any`、`not`、`event_type`、`min_confidence`、`stable_for_ms`、`within_ms`、`source_camera_role` 和已注册的外部信号条件。不得允许任意函数调用、文件/网络访问或动态代码执行。

#### 6.4.1 状态迁移矩阵

Agent 必须实现并测试以下默认迁移矩阵；SOP DSL 可细化允许的路径，但不得绕过全局不变量。

| 当前状态 | 输入/条件 | 下一状态 | 动作 |
|---|---|---|---|
| `PENDING` | 所有前置依赖已完成，收到有效开始证据 | `IN_PROGRESS` | 记录开始时间与证据 |
| `PENDING` | 前置依赖未完成，却收到该步骤完成事件 | 保持 `PENDING` | 产生错序/意外步骤告警 |
| `IN_PROGRESS` | 完成条件满足且证据通过校验 | `COMPLETED` | 保存结果、证据引用和判定理由 |
| `IN_PROGRESS` | 超时且策略要求告警 | `IN_PROGRESS` 或 `NEEDS_REVIEW` | 创建超时告警；不得自动判为完成 |
| `IN_PROGRESS` | 证据冲突或不足 | `NEEDS_REVIEW` | 保留证据并等待确认 |
| `PENDING` / `IN_PROGRESS` | 显式人工跳过且步骤允许跳过 | `SKIPPED` | 记录操作者、原因与审计记录 |
| `IN_PROGRESS` | 明确失败证据且规则定义失败处理 | `FAILED` 或 `NEEDS_REVIEW` | 按版本化规则处理 |
| 所有非终态 | 执行实例被显式暂停 | 不变步骤状态，执行状态 `PAUSED` | 暂停计时策略按 SOP 定义 |
| `COMPLETED` / `ABORTED` | 普通迟到事件 | 不变 | 记录迟到事件，不回退状态 |

> **1.1 校订（作废）**：上表要求先有“开始证据”才能进入 `IN_PROGRESS`，但瞬时事件步骤没有开始证据。架构基线允许隐式激活与 `PENDING → COMPLETED` 原子迁移；`IN_PROGRESS` 在架构基线中称 `ACTIVE`，超时落到 `TIMED_OUT`。见 ADR-0001 A4、A12。

`SOPExecution` 的 `COMPLETED` 只有在所有必需步骤完成、可选步骤按策略处理且无阻塞性待确认项时才允许进入。可选步骤未执行不等于失败；并行步骤只有在其依赖和完成策略满足后才能解锁后续汇合节点。

#### 6.4.2 并行与可选步骤

- 流程使用 DAG；每一步声明 `depends_on`，允许多个步骤在前置条件满足后并行进入 `IN_PROGRESS`。
- 汇合节点的策略必须明确为 `ALL_REQUIRED` 或受限的 `ANY_OF_N`，不能靠 `sequence` 推断。
- 可选步骤必须声明跳过条件/完成策略，并在执行记录中记录 `SKIPPED` 与原因。
- 发布 SOP 版本前，必须校验 DAG 无环、所有引用的步骤存在、起点/终点有效、所有必需步骤可达、条件字段合法。
- DSL v1 不支持任意循环；需要返工时使用显式分支，或终止当前执行并创建新的执行实例。

#### 6.4.3 多相机证据关联与冲突处理

首版采用**规则驱动的事件关联**，不默认使用跨相机深度融合模型，也不简单平均不同相机的置信度。每个工位的 `StationCameraBinding` 必须声明相机 `role`（例如 `overview`、`hands`、`tool`、`part_state`）和允许支持的事件类型。

默认处理规则：

1. 事件必须先按 `station_id`、事件类型、事件时间和相机绑定关系筛选候选来源；时间窗口由事件类型/工位策略配置，不使用全局固定窗口。
2. 同一动作在多相机中重复检测时，通过 `correlation_key`（若可生成）、事件类型、时间窗口和对象/跟踪线索进行去重。没有足够证据证明是同一动作时，不得仅因时间接近就删除事件。
3. 对某一步骤的完成条件，DSL 可以指定必需的相机角色、至少需要的独立证据数、允许的时间差和优先来源。单一相机的低置信度结果不能覆盖必需的另一视角证据。
4. 相互独立且一致的证据可以共同满足步骤条件；不同相机结论冲突时，按步骤显式定义的优先级/规则处理。若无明确规则或冲突仍存在，结果必须进入 `NEEDS_REVIEW`，不得自动判定合格。
5. 每个融合判定必须保留来源事件 ID、相机 ID、时间戳、使用的规则版本和判定理由，以支持追溯。
6. 首版不做自动标定/几何重建式多视角融合；如未来需要，应作为独立能力通过 ADR 引入。

### 6.5 不允许的实现

- 不得通过 `if event_type == ...` 的散落条件拼成不可测试的全局流程。
- 不得在模型推理代码里推进步骤。
- 不得将 SOP 步骤逻辑硬编码到前端。
- 不得把 VLM 的自然语言回答直接作为最终合规状态；必须转换为有类型结果并进行规则校验。
- 不得以一个置信度阈值覆盖所有工位和所有事件；阈值应由模型/事件/工位策略配置。

---

## 7. 数据持久化与一致性

### 7.1 数据库是业务事实来源

PostgreSQL 保存：
- 工位、相机及绑定配置；
- SOP 定义与版本；
- SOP 执行实例及步骤结果；
- 标准化事件（按保留策略存储）；
- 告警、确认记录和审计记录；
- 模型版本/推理配置的元数据；
- 证据文件的引用、时间戳、校验和。

视频/图像大文件存放在文件系统或对象存储适配层，数据库仅存 URI、元数据和校验信息。

### 7.2 事务规则与 Outbox 一致性

- 一次 SOP 状态迁移、步骤结果写入、关联告警创建，以及待发送的 WebSocket/集成通知 Outbox 记录，应在同一个数据库事务中完成。
- **禁止在数据库事务提交前推送外部消息；禁止只提交数据库而直接依赖内存回调完成通知。**
- Outbox 表至少包含 `id`、`event_type`、`aggregate_type`、`aggregate_id`、`payload`、`created_at`、`published_at`、`attempt_count`、`last_error`。首版可由后台轮询任务发布，发送成功后标记完成；重复发送由消费者/前端按消息 ID 幂等处理。
- Outbox 是可靠通知的来源；WebSocket 仅是实时展示通道，客户端重连后应通过 REST API 重新读取权威状态。不能把“消息已发到 WebSocket”当作持久化成功。
- 幂等键/唯一约束用于防止重复事件产生重复步骤完成或重复告警。
- 并发更新 `SOPExecution` 时采用乐观锁（`version`）或等价并发控制，防止两个事件同时推进同一执行实例。
- 数据库迁移必须通过 Alembic；禁止应用启动时自动删除/重建表。
- 已发布 SOP 版本不可原地修改。
- 所有时间使用带时区的时间类型，并统一采用 UTC 存储；展示层按用户/工厂时区转换。

### 7.3 证据写入一致性

证据文件存储与 PostgreSQL 事务无法天然组成单一 ACID 事务，必须采用可恢复的两阶段流程：

1. 先将证据写入临时/待提交位置，计算 SHA-256，记录大小、媒体类型和时间戳。
2. 完成必要的文件写入校验后，在数据库事务中写入证据元数据、业务判定、告警和 Outbox 记录；证据状态标记为 `PENDING_COMMIT`。
3. 事务提交后，将文件提升/标记为正式证据并将元数据状态更新为 `AVAILABLE`。
4. 若数据库提交失败，清理临时文件；若文件已提交但状态更新失败，由后台 reconciliation job 根据证据 ID 和校验和重试修复。
5. 告警可引用 `PENDING` 证据，但前端必须显示证据尚不可用，不能伪装成可回放。证据缺失必须生成系统告警或可观测错误。

首版可以用本地文件系统实现该协议，但必须通过 `EvidenceStore` 接口隔离，以便未来切换对象存储。

### 7.4 事件留存策略

不要默认永久保存所有原始帧、全部模型输出和所有视频。必须区分：
- 业务事件：按业务追溯要求保存；
- 告警证据：按保留策略保存图片/短视频；
- 原始视频：默认不永久存储，需显式配置保留策略；
- 调试日志：不得包含秘密、口令或不必要的个人信息。

---

## 8. 相机与推理运行时约束

### 8.1 设备适配接口

所有设备适配器必须实现统一生命周期（接口名称可依实现调整，但语义不得改变）：

```python
class FrameSource(Protocol):
    async def open(self) -> None: ...
    async def read(self) -> "Frame | None": ...
    async def close(self) -> None: ...
    async def health(self) -> "SourceHealth": ...
```

`Frame` 至少包含：
- `camera_id`
- `sequence`
- `captured_at`
- `image` 或可管理的帧引用
- `width`、`height`、`pixel_format`

具体实现可使用 OpenCV、厂商 SDK 或 GStreamer，但业务层只能依赖 `FrameSource` 契约。

### 8.2 推理运行时接口

```python
class InferenceRuntime(Protocol):
    async def start(self) -> None: ...
    async def submit_frame(self, frame: Frame) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> "RuntimeHealth": ...
```

事件输出通过明确的异步队列/回调适配器传递，必须设置队列容量和背压策略，不能无限堆积帧。

### 8.3 视频实时性策略

- SOP 监控通常不需要每帧执行每个模型；采样策略必须可配置。
- 实时检测优先处理最新帧时，可采用有界队列和旧帧丢弃策略；但用于动作时序识别的窗口必须保留所需序列，不能任意丢帧破坏时序语义。
- 明确区分“帧采集时间”“模型完成时间”和“事件发生时间”。
- 采集断线、推理异常、GPU OOM、队列积压必须生成可观测的健康状态/系统告警。
- 模型预热、加载失败和重启应可观测；不得把启动未完成误报为“无缺陷/合规”。
- 相机、模型、工位都必须有独立健康状态。

### 8.4 DeepStream 接入准则

只有在真实基准测试显示 Python/OpenCV 路径不能满足多路吞吐、GPU 利用率、延迟或资源占用要求时，才实现 DeepStream Runtime。

引入前必须记录：
- GPU 型号、驱动、CUDA、TensorRT、DeepStream 版本；
- 相机接口及 SDK 兼容性；
- 每路分辨率、帧率、推理采样率；
- 端到端延迟、GPU/CPU/内存占用；
- 断线重连和异常恢复测试结果。

DeepStream 适配不得改变标准事件 schema 或 SOP 状态机接口。

---

## 9. API 与前端通信约束

### 9.1 API 分组

API 路由至少按以下领域分组（不设版本段）：
- `/stations`
- `/cameras`
- `/sops`
- `/executions`
- `/alarms`
- `/events`
- `/system`

具体 endpoint 可随实现完善，但必须有统一的错误格式、分页规则和 schema 验证。

### 9.2 WebSocket

WebSocket 只推送状态变化、告警变化、健康状态和轻量级事件摘要，不通过 WebSocket 发送连续全分辨率视频帧。

消息至少包含 `schema_version`、`message_type`、`occurred_at` 和业务对象标识。

### 9.3 前端约束

- React 页面只负责呈现与交互，不负责判定 SOP 是否合格。
- API 请求和领域类型集中管理，不在多个组件里重复定义同一接口 schema。
- 摄像头画面与 SOP 状态应可独立刷新；视频源暂时不可用时仍需展示设备故障状态。
- 所有告警应明确区分工艺异常与系统故障。
- 不得把模型置信度直接显示为“工艺合格率”，除非有明确统计定义。

---

## 10. 建议目录结构

> **1.1 校订（示意）**：本节目录仅表达模块依赖，不是迁移指令。落地目录以架构基线 §4 与 `docs/implementation/README.md` 的映射为准，不要按本树重建项目。

```text
ai-sop-platform/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   │   ├── stations/
│   │   │   ├── cameras/
│   │   │   ├── sops/
│   │   │   ├── executions/
│   │   │   ├── alarms/
│   │   │   └── history/
│   │   ├── components/
│   │   ├── lib/
│   │   └── api/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   │   ├── stations/
│   │   │   ├── cameras/
│   │   │   ├── sops/
│   │   │   ├── executions/
│   │   │   ├── events/
│   │   │   ├── alarms/
│   │   │   └── evidence/
│   │   ├── infrastructure/
│   │   │   ├── database/
│   │   │   ├── messaging/
│   │   │   └── storage/
│   │   └── repositories/
│   ├── migrations/
│   └── pyproject.toml
├── inference/
│   ├── main.py
│   ├── sources/
│   ├── sampling/
│   ├── pipelines/
│   ├── models/
│   ├── event_builders/
│   └── runtimes/
├── contracts/
│   ├── events/
│   └── api/
├── configs/
│   ├── stations.example.yaml
│   └── sops/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── scenarios/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ADR/
│   └── RUNBOOK.md
├── docker-compose.yml
├── .env.example
└── README.md
```

目录可按项目实际打包方式微调，但模块依赖方向必须遵守第 11 节。

---

## 11. 依赖方向与编程约束

### 11.1 允许的依赖方向

```text
API / UI
   ↓
Application Services
   ↓
Domain (SOP, Station, Event, Alarm)
   ↑
Ports / Interfaces
   ↑
Infrastructure Adapters (DB, camera SDK, runtime, messaging)
```

更具体地说：

- `domain` 不得导入 FastAPI、SQLAlchemy、OpenCV、PyTorch、DeepStream 或前端代码。
- `application` 可调用领域逻辑和抽象接口，不得依赖具体相机 SDK。
- `infrastructure` 实现领域/应用定义的接口。
- `api` 负责协议解析、参数校验和调用应用服务，不承载 SOP 判定。
- `inference` 只负责采集、推理和构建标准化事件，不直接写业务数据库。
- `contracts` 只放跨进程/跨模块的稳定 schema，不放业务执行逻辑。
- 禁止循环依赖；禁止用全局单例隐藏状态依赖。

### 11.2 Python 约束

- Python 3.11+；正式依赖版本应锁定并通过项目锁文件管理。
- 使用类型标注；公共接口必须有类型。
- API 和事件 schema 使用 Pydantic。
- 数据库访问使用 SQLAlchemy 2.x；迁移使用 Alembic。
- 领域核心优先使用纯 Python 类型/数据类，避免 ORM 对象渗透领域层。
- 使用 `async` 时必须遵守异步边界；CPU/GPU 阻塞推理不能直接阻塞 FastAPI event loop。
- 不得使用 `except Exception: pass` 等吞异常写法。
- 所有外部资源（相机、文件、数据库会话、推理进程）必须有明确生命周期与关闭路径。
- 禁止把任意 Python 代码作为 SOP 配置执行；规则配置必须是受限、可校验的数据结构。

### 11.3 TypeScript/React 约束

- 使用 TypeScript strict mode。
- API 类型集中管理，优先由 OpenAPI schema 生成或验证客户端类型，避免前后端手工维护重复定义。
- 页面组件不实现 SOP 领域规则。
- 网络请求必须有加载、错误和断线状态；关键状态不允许仅存在于浏览器内存。
- 组件不得直接访问数据库或相机 SDK。

### 11.4 配置与秘密管理

- 所有环境相关配置通过环境变量或配置文件注入。
- 提供 `.env.example`，不得提交真实凭据。
- 相机地址、模型路径、采样策略和 SOP 版本不得散落硬编码在源代码中。
- 配置启动时必须验证；错误配置应快速失败并给出可操作错误信息。
- 生产日志中不得记录密码、访问令牌或敏感视频数据。

---

## 12. 可靠性、可观测性与故障处理

必须至少具备以下能力：

#### 12.1 健康状态枚举

相机、推理运行时、应用后端和数据库分别维护健康状态，不能用单个系统级布尔值代替。统一基础枚举：

- `UNKNOWN`：尚未检查或状态未知；
- `STARTING`：初始化/模型加载中；
- `HEALTHY`：在约定时间窗内正常工作；
- `DEGRADED`：仍可工作但帧率、延迟、丢帧或错误率超过告警阈值；
- `UNAVAILABLE`：连接断开、进程退出或核心能力不可用；
- `MISCONFIGURED`：配置、驱动或依赖不合法；
- `STOPPED`：由操作者正常停止。

健康状态变化必须记录 `component_type`、`component_id`、`previous_status`、`current_status`、`reason_code`、`occurred_at` 和关联诊断信息。

#### 12.2 告警分类

告警 `category` 至少区分：

- `PROCESS_COMPLIANCE`：漏步、错序、超时等工艺异常；
- `VISION_QUALITY`：遮挡、证据不足、模型置信度不足、视野失效；
- `DEVICE_HEALTH`：相机断线、采集失败；
- `INFERENCE_HEALTH`：模型加载失败、GPU OOM、推理超时；
- `PLATFORM_HEALTH`：数据库、存储、消息发布、API 等系统故障；
- `CONFIGURATION`：SOP/相机/模型配置错误。

告警另有 `severity`（`INFO`、`WARNING`、`ERROR`、`CRITICAL`）、`status`（`OPEN`、`ACKNOWLEDGED`、`RESOLVED`、`SUPPRESSED`）、`source_id`、`first_seen_at`、`last_seen_at`、`occurrence_count`。工艺异常和系统健康告警不得混为一类。

#### 12.3 可观测性最低要求

- 结构化日志，包含 `station_id`、`camera_id`、`execution_id`、`event_id`（适用时）。
- 相机连接、最后一帧时间、帧率、丢帧、推理延迟和队列长度等基础指标。
- 模型加载/卸载状态、GPU 错误和推理异常记录。
- 系统故障告警与工艺异常告警分离。
- API、数据库和推理运行时健康检查。
- 对相机断线实施有限重试与退避；重连后恢复状态，不自动重置 SOP 执行。
- 对事件发送实施有界重试；达到上限后记录失败并提供可恢复路径。
- 日志不得替代业务事件表；业务事件也不得替代调试日志。

第一阶段可以使用结构化日志和简单指标，不强制部署 Prometheus/Grafana 全套系统。

---

## 13. 安全与工业现场边界

### 13.1 认证与授权基线

PoC 可以只部署在受控的本地开发网络，但架构不得将“无认证”写死：

- 所有写操作（创建/修改工位、发布 SOP、启动/停止执行、人工确认/跳过、修改保留策略）必须经过认证和授权中间件。
- 定义最小角色：`VIEWER`（只读）、`OPERATOR`（运行/确认）、`ENGINEER`（配置/测试）、`ADMIN`（用户和系统管理）。角色权限通过统一策略检查，不在每个路由中散落硬编码判断。
- 未配置认证时，只允许显式的 `APP_ENV=development` 且监听回环地址或受控开发环境；生产环境启动时缺少认证配置必须失败。
- 人工确认/跳过必须记录 `actor_id`、时间、理由、执行实例、步骤和证据引用。
- 证据读取必须经过授权 API 或短期有效的受控访问 URL；禁止直接暴露任意本地文件路径或公开目录。
- 对 RTSP 地址、相机凭据、令牌和密钥进行脱敏；秘密不得出现在日志、错误响应和前端配置中。

### 13.2 工业安全边界

- AI-SOP 用于作业指导、质量监控和异常提示，不是安全认证系统。
- 不得以模型输出直接驱动危险运动、解除安全互锁或取代 PLC 安全逻辑。
- PLC/工具控制器接入需使用独立适配器和明确的数据质量/超时规则。
- 视频和证据数据应按工厂隐私及保留策略管理。
- 生产环境需有认证、授权和审计；PoC 可简化登录，但不能把无认证设计写死在业务层。
- API 不得向未经授权的客户端暴露 RTSP 凭据、相机秘密或本地文件路径。

---

## 14. 测试策略与验收标准

### 14.1 必须有的测试

1. **领域单元测试**：合法/非法状态迁移、漏步、错序、超时、重复事件、复位。
2. **幂等测试**：同一 `event_id` 重复到达不会重复推进步骤或重复创建告警。
3. **乱序测试**：迟到事件不会无条件回退已完成状态。
4. **并发测试**：同一执行实例同时收到多个事件时，状态不会丢失或重复推进。
5. **适配器契约测试**：视频文件源、RTSP 源、厂商 SDK 源输出统一 `Frame` 契约。
6. **API 集成测试**：配置、执行、告警、事件查询和错误处理。
7. **故障测试**：相机断线、模型崩溃、数据库暂时不可用、推理队列积压。
8. **端到端场景测试**：正常操作、漏步、错序、重复操作、遮挡、不同人员和不同操作速度。
9. **多工位隔离测试**：一个工位的事件不能改变另一个工位的执行状态。

### 14.2 视觉算法评估

不能只报告整体 accuracy。至少报告：
- 各步骤 precision / recall；
- 漏步、错序检出率；
- 误报警率与漏报警率；
- 事件识别延迟与端到端告警延迟；
- 不同人员、速度、视角、遮挡条件下的表现。

训练集与测试集必须按视频/人员/采集批次划分，避免相邻帧泄漏导致虚高成绩。

### 14.3 首阶段验收

首阶段必须能做到：
- 从视频文件回放一个完整 SOP 周期。
- 配置一个工位、一个相机、至少 4 个步骤。
- 正确推进正常步骤。
- 检出至少一种漏步和一种错序场景。
- 对重复事件保持幂等。
- 将执行记录和告警保存到 PostgreSQL。
- 前端实时显示当前步骤、执行状态和告警。
- 在不修改 SOP 领域代码的情况下替换或模拟一个视觉事件生产者。

以上是工程验收条件，不代表视觉模型已经达到量产精度。

---

## 15. 实施阶段（功能递增，架构不变）

### Phase 0：仓库与环境基线
- 建立仓库、锁定 Python/Node 版本和依赖。
- 启动 PostgreSQL、迁移系统、健康检查。
- 建立 `contracts` 和领域测试。
- 暂不接真实相机。

### Phase 1：SOP 业务闭环（可用模拟事件）
- 实现 Station、SOPDefinition/SOPVersion、SOPExecution、StepResult、Alarm。
- 用模拟事件驱动状态机。
- 完成幂等、乱序、错序、漏步、超时和复位测试。
- 提供最小 API 与 Web UI。

### Phase 2：单路视频 PoC
- 接入文件视频和一种简单采集源。
- 实现 FrameSource、采样策略、一个基线模型和 Event Builder。
- 验证视频时间戳到告警的端到端链路。

### Phase 3：多工位/多相机模拟
- 用多路文件视频模拟不同工位和相机。
- 验证工位状态隔离、队列背压、断线/重启和资源监控。

### Phase 4：真实相机与算法提升
- 接入目标工业相机 SDK。
- 用真实视频数据评估模型；按工位选择检测、跟踪、时序识别或 VLM。
- 需要时评估 NVIDIA SOP Monitoring Blueprints 的时序检测/VLM 路线。

### Phase 5：性能与部署优化
- 测量真实分辨率、帧率、路数、延迟、GPU/CPU/内存占用。
- 只有测量结果证明有必要时，增加 DeepStream/Osprey 适配。
- 根据可靠性需求再决定是否引入持久化消息队列、独立部署更多服务或集中式监控。

各阶段不能通过绕开领域模型或硬编码工位来“快速交付”。

---

## 16. 架构变更流程（ADR）

任何涉及以下内容的修改都必须先写 Architecture Decision Record（ADR）：
- 改变核心技术栈；
- 拆分/合并运行进程；
- 修改事件契约或 SOP 状态模型；
- 更换数据库或消息传输机制；
- 引入 DeepStream、Osprey、Kafka、Redis 等关键基础设施；
- 改变数据保留、可靠性或安全策略。

ADR 至少包含：
1. 背景与问题；
2. 当前决策；
3. 候选方案；
4. 取舍和成本；
5. 对现有代码/数据的影响；
6. 测试和回滚计划。

建议路径：`docs/ADR/NNNN-short-title.md`。

AI Agent 不得自行认定“重构更干净”就更改基线；必须先提出 ADR 并等待用户批准。

---

## 17. Agent 每次编码任务的执行协议

接到开发任务后，AI Agent 必须：

1. 阅读本文件及相关 ADR。
2. 检查当前代码、依赖、测试和 Git diff；先理解再修改。
3. 将任务映射到明确模块，确认不会跨越禁止的依赖边界。
4. 如果需求与架构冲突，先说明冲突并提出 ADR，不得静默改架构。
5. 先定义/更新 schema 和测试，再实现业务逻辑。
6. 采用最小、可验证的改动；不进行无关重构，不批量改名。
7. 执行相关测试、lint、类型检查和构建；报告命令与结果。
8. 汇报变更文件、关键实现、未完成事项、风险和后续建议。
9. 不得伪造测试结果、基准数据、模型准确率或硬件兼容结论。
10. 如果缺少必要的硬件/业务信息，使用模拟适配器推进非依赖部分，并把未验证项明确列出。

---

## 18. 初始技术与依赖政策

- Python：采用当前项目兼容的 Python 3.11+ 版本；所有依赖必须锁定。
- 后端：FastAPI、Pydantic、SQLAlchemy 2.x、Alembic、PostgreSQL 驱动。
- 前端：React、TypeScript strict、Vite；具体 UI 库可在 ADR 或前端规范中单独决定。
- 推理：PyTorch/ONNX Runtime 等按模型和硬件选择；不预先承诺某一推理后端。
- 相机：OpenCV 仅作为一种适配器，不是领域层依赖。
- 测试：pytest；前端采用相应单元/组件测试工具。
- 代码质量：格式化、lint、类型检查纳入项目命令与 CI。
- 不添加未经需求证明的框架；引入每项基础设施必须说明解决的实际问题。

具体版本必须在初始化项目时核实兼容性并写入锁文件；不得把“最新版”作为唯一版本策略。

---

## 19. 前后端契约生成、证据保留与运维策略

### 19.1 Schema 生成链

- 后端 Pydantic 模型是 REST API 的权威 schema 来源；FastAPI 生成 OpenAPI。
- 前端 API 类型通过 OpenAPI 生成工具从已版本化的 OpenAPI 文档生成，不得长期手工维护重复的请求/响应类型。生成文件标记为自动生成，禁止直接编辑。
- 跨进程事件契约在 `contracts/events` 中定义，并通过 Pydantic schema 校验；若使用 JSON Schema/TypeScript 类型生成，生成步骤必须纳入项目命令和 CI。
- CI 必须检测生成结果是否过期：重新生成后若产生 diff，检查失败。
- WebSocket 消息也必须使用有版本的 schema，并纳入契约测试。
- schema 的破坏性变更必须提升版本并提供迁移/兼容策略；不能只改后端而假设前端同步更新。

### 19.2 数据与证据保留策略基线

保留时长是部署配置，不能散落在业务代码中。首版提供可覆盖的默认值：

| 数据类型 | 默认策略（PoC 初始值） | 约束 |
|---|---|---|
| SOP 执行、步骤结果、人工确认审计 | 默认长期保留，PoC 至少 180 天 | 生产时按质量追溯/法规要求确认 |
| 工艺异常与系统告警 | 至少 180 天 | 允许按类别单独配置 |
| 告警证据图片 | 30 天 | 被调查/锁定的证据可设置 legal hold/保留锁 |
| 告警前后短视频 | 默认关闭；启用后 7 天 | 只保存配置的前后时间窗，设置容量上限 |
| 非告警原始视频 | 默认不持久化 | 仅调试或经授权的采集任务可临时保存 |
| 调试日志 | 14 天 | 不记录秘密和不必要的个人信息 |
| 原始高频模型观测 | 默认不长期保存 | 只保存汇总、触发事件附近样本或明确指定的调试样本 |

这些值只是可落地的 PoC 默认值，不是对生产法规的判断。生产部署前必须由用户/工厂确认。清理任务应有 dry-run、删除统计、失败重试和审计记录；证据删除不得破坏仍需保留的审计元数据。

### 19.3 事件关联与执行周期规则（强制）

事件进入 SOP 状态机前必须经过 `ExecutionResolver`，不能依赖模型猜测 `execution_id`。

1. 若事件已经携带有效 `execution_id`，验证它存在、属于相同工位、状态允许接收事件，且事件时间位于该执行实例有效窗口内。验证失败则隔离，不允许自动改绑。
2. 若事件没有 `execution_id`，仅允许在以下条件全部满足时自动关联：存在唯一活动执行实例；`station_id` 明确；事件时间位于执行实例窗口及配置的迟到容忍窗口内；来源相机已绑定该工位；没有工件/周期边界冲突。
3. 如果活动执行实例为零或多于一个，或任何条件存在歧义，事件进入 `UNASSIGNED`/隔离状态并产生可追踪记录；不得任选最近执行实例。
4. 每个执行实例有 `started_at`、`finished_at`、`accept_events_until`（可配置的迟到宽限截止时间）和 `version`。终态执行实例不接受普通事件改变状态。宽限期内的迟到事件只能补充证据或产生复核，不得自动回退已完成步骤。
5. 开始新执行实例必须由明确的开始命令、条码/工件识别、PLC 周期信号或经过验证的周期边界触发。模型短暂漏检不能自动重置执行实例。
6. `Observation.execution_id` 可为空；一旦事件被路由为 `RoutedSOPEvent`，`execution_id` 必须非空。关联决策必须记录 `resolution_method`、`resolved_at` 和规则版本。
7. 同一事件只允许关联一个执行实例；若多工位/多执行实例均可能匹配，必须隔离并人工确认。

## 20. 未决事项（不得由 Agent 猜测）

在真实相机和工艺试点前，以下内容需要根据实际情况确认：

- 目标相机类型、厂商 SDK、操作系统和驱动版本。
- 需要同时处理的相机路数、分辨率、帧率、曝光和同步要求。
- GPU 型号、显存和部署主机配置。
- 工位是否需要产品 ID/条码/PLC 信号来定义一次 SOP 周期。
- 各步骤允许的检测延迟和告警延迟。
- 生产环境最终证据保留时长、隐私要求，以及是否存在法规/客户特殊要求（PoC 默认值见第 19.2 节）。
- 生产环境实际身份提供方与角色映射（认证/授权架构基线见第 13.1 节）。
- 人工确认、告警升级和工位复位的现场流程。
- 不同工位的具体 SOP 步骤、可观测特征和合格标准。
- 生产环境的账号权限、网络隔离和部署限制。

这些未决事项不阻止先实现核心领域模型、模拟事件闭环和文件视频 PoC；但在硬件/量产性能决策上必须先实测，不能臆测。

---

## 21. 架构基线总结

本项目的稳定核心是：

1. **模块化单体业务后端**：首版简单，领域边界清晰。
2. **独立推理运行时**：隔离模型/GPU/采集故障，支持替换推理后端。
3. **标准化事件契约**：模型输出不直接控制业务状态。
4. **每工位独立 SOP 执行状态机**：支持多工位、多相机、不同工艺。
5. **PostgreSQL 持久化业务事实**：配置、版本、执行、事件、告警可追溯，并用事务 Outbox 保证通知可恢复。
6. **先用文件视频和模拟事件落地，再接真实相机和性能优化**：不牺牲长期架构换取短期演示。
7. **受限 SOP DSL + DAG 状态迁移**：显式支持必需/可选/并行步骤，发布前静态校验。
8. **执行实例关联必须确定且可审计**：有歧义就隔离，禁止猜测绑定。
9. **事务 Outbox + 可恢复证据存储流程**：数据库状态、通知与证据可检测、可重试、可修复。
10. **健康告警、权限和 schema 生成链有统一约束**：避免系统故障与工艺异常混淆及前后端契约漂移。

任何技术选型都服务于上述架构原则。系统允许模型、设备和推理引擎变化，但不得让这些变化穿透到 SOP 领域核心。
