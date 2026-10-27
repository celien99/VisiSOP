# 50 视频运行时（Video Runtime）

**基线**：§2.2 进程边界、§3 开源吸收、§12 管线与接口、§15 部署
**约束参考**：§8 运行时约束
**阶段**：2（阶段 3 接真实相机，阶段 4 做性能 Spike）
**依赖**：10 contracts

## 落点

```text
runtime/
├── pyproject.toml                  # workspace 成员，包名 video_runtime，依赖 contracts
└── video_runtime/
    ├── main.py                     # 进程入口：装配 source → buffer → sampler → backend → recognizer → builder → publisher
    ├── sources/                    # VideoSource；FileSource 先行，RTSP / 厂商 SDK 后加
    ├── sampling/                   # 抽帧、ROI、按工位/相机策略
    ├── inference/                  # InferenceBackend 协议 + PythonBackend
    ├── recognition/                # 检测/跟踪/时序识别器；阶段 2 用模拟识别器
    ├── event_builder/              # RawInferenceResult → VisionEvent（唯一出口）
    ├── evidence/                   # 关键帧捕获、SHA-256、临时落盘
    └── health/                     # runtime_id、心跳、指标
```

根 `pyproject.toml` 的 workspace members 增加 `runtime`。基线的 `apps/video_runtime` 与 `runtime/` 合并为本目录（D9）。

## 管线（基线 §12.1）

```text
SourceAdapter → FrameBuffer（有界）→ FrameSampler → InferenceBackend
→ Recognizer → EventBuilder → (EvidenceCapture, EventPublisher → API)
```

- `FrameBuffer` 必须有界并声明背压/丢帧策略；实时检测可丢旧帧，时序窗口不许丢。
- 采样按相机/工位/模型配置，不默认每帧跑全部模型。
- `Frame` 必带 `camera_id`、`frame_seq`（单调）、`captured_at`、宽高、像素格式。

## 接口（基线 §12.2）

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

- 概念接口，不逐字照搬；实现时必须明确 async/thread 模型、帧内存生命周期、关闭顺序。
- 关键帧写入与 backend 共享的 `EVIDENCE_DIR/tmp/{event_id}.*`，事件只带键（A10）；runtime 不建 `evidence_assets`、不决定证据是否 `AVAILABLE`。
- 投递：`POST /events`，`event_id` 即幂等键；有界重试 + 有限本地持久化，超限上报丢失计数与健康告警。
- 退出时关闭所有 source、backend、publisher；启动/模型加载失败必须可观测，不得显示为“合规”。

## 开源组件边界（基线 §3）

- DeepStream / Osprey 只能作为 `InferenceBackend` 或 `VideoRuntimeAdapter` 的实现；`NvDs*`、GStreamer、Osprey 内部类型不得出现在事件契约或 API。
- SOP Monitoring Blueprints 只能作为 `Recognizer`/`TemporalRecognizer` 的候选实现，输出必须转成 `Observation` / `VisionEvent`。
- 阶段 4 才做 Spike；进入正式部署前记录版本矩阵、吞吐/延迟/GPU 基准与回滚方案（基线 §18）。
- 阶段 2 只实现 `FileSource` + `PythonBackend` + 模拟识别器，不为未测量的性能问题预写后端。

## 运行时健康与注册（基线 §15.2）

- 启动后向 API 注册 `runtime_id`、负责的相机列表、版本；定期心跳。
- 重启后重新声明相机状态，不把重启前内存状态当事实。
- 指标：每路 FPS、采样 FPS、推理延迟、丢帧、事件发送失败/重试、队列长度。

## 不做

- 不导入后端 ORM、不写 PostgreSQL 业务表、不调用 SOP 引擎；
- 不做多相机几何融合、真实模型精度承诺；
- 不在运行时内实现业务判定。

## 测试（基线 §17.1 Runtime 层）

- 适配器契约测试：文件源与 fake 源输出同一 `Frame` 形状；
- 采样、背压、丢帧策略、关闭顺序单测；
- 端到端：文件回放 → 事件通过 contracts 校验 → 后端推进 SOP；
- 故障：源断开/重连、backend 超时、投递失败重试、队列积压。

## DoD

`python -m video_runtime.main` 从文件回放驱动 30 完成一次 SOP 周期；事件顺序、幂等、重连后继续均有测试。
