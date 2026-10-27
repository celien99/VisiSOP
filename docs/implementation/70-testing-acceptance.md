# 70 测试与验收

**基线**：§17 测试层与 PoC 验收、§18 实施阶段
**约束参考**：§14 测试清单
**阶段**：贯穿（20 开工即可搭骨架）
**依赖**：各工作包

## 分层（基线 §17.1）

| 层 | 位置 | 内容 |
|---|---|---|
| 契约 | `contracts/tests/` | 三类事件与 WS 信封的 schema、版本兼容、未知类型拒绝 |
| 领域 | `backend/tests/domain/` | DAG、迁移矩阵、并行汇合、可选跳过、超时、多相机冲突 |
| 仓储/事务 | `backend/tests/integration/` | 幂等 receipts、Outbox 原子写入、并发迁移、回滚 |
| API | `backend/tests/api/` | §11.1 端点、错误格式、关联隔离 |
| 运行时 | `runtime/tests/` | 文件回放、断线重连、背压、模型超时、投递失败 |
| 场景回放 | `tests/scenarios/*.json` | 事件脚本 → 期望步骤/告警序列（阶段 1 验收主抓手） |
| 端到端 | `frontend/tests/` | 总览 → 执行时间线 → 告警 → 复核 |
| 故障 | `backend/tests/faults/` | API/Runtime 重启、DB 暂不可用、乱序/重复/迟到、证据中断 |

## 场景脚本格式

```json
{
  "name": "parallel-bolts-normal",
  "sop": "sop_dsl/examples/seat_assembly_basic.yaml",
  "events": [
    { "at_ms": 0, "type": "frame_placed", "camera_role": "overview", "confidence": 0.95 },
    { "at_ms": 800, "type": "left_bolt_installed", "camera_role": "hands", "confidence": 0.93 },
    { "at_ms": 1200, "type": "right_bolt_installed", "camera_role": "hands", "confidence": 0.93 }
  ],
  "expect": {
    "steps": ["place_frame:COMPLETED", "install_left_bolt:COMPLETED", "install_right_bolt:COMPLETED", "verify_both_bolts:COMPLETED"],
    "alarms": []
  }
}
```

- `at_ms` 相对执行开始；`event_id`、`station_id`、`camera_id`、`frame_seq` 由夹具生成。
- **同一脚本必须能在“纯领域”和“经 API”两种模式下跑出相同结果**，同时验证 D3（引擎纯函数）与 §9 持久化语义。
- 场景覆盖：正常线性、并行汇合、可选跳过、漏步、错序、重复、迟到、多相机冲突、证据缺失、隔离改绑。

## PoC 验收（基线 §17.2）

1. 固定样例视频可重复运行同一 SOP，得到可解释、可复现的步骤时间线；
2. 同一 `event_id` 重复投递不重复完成步骤或告警；
3. 无法关联执行实例的事件不推进 SOP；
4. 每个完成/异常步骤可查看来源事件、规则版本与证据状态；
5. Runtime/相机故障显示为系统健康告警，不伪装成工艺违规；
6. OpenAPI/前端类型生成链同步，CI 检测生成文件过期；
7. 模拟相机与事件闭环后，再进入真实相机验证。

量化门槛与上述条目同时验收：10,000 条脚本事件 0 丢失、同一 `event_id` 重放 10 次恰好 1 次迁移与 1 条告警、事件 `POST` 提交 p95 ≤ 100 ms、状态到 WS 推送 p95 ≤ 300 ms（本地单工位）。

## 阶段门槛（基线 §18）

| 阶段 | 测试门槛 |
|---|---|
| 1 业务闭环 | 领域 + 契约 + 仓储/API；模拟事件跑通完整周期 |
| 2 视频回放 | 运行时 + 场景回放；视频驱动状态变化 |
| 3 真实相机 | 断线重连、时间戳、帧率、证据质量 |
| 4 性能 Spike | 吞吐/延迟/GPU 基准，不阻塞主干 |
| 5 多工位试点 | 隔离、权限、备份恢复、容量监控 |

## 不做

不在没有数据时写算法精度报告。约束参考 §14.2 的 precision/recall 与按人员/批次划分评估属于阶段 4。

## DoD

CI 覆盖率 ≥90%；`tests/scenarios/` 纳入根 `scripts/test.sh`；失败时输出实际步骤序列与原因码。
