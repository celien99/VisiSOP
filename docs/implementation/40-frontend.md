# 40 前端

**基线**：§11.3 预览与证据分离、§13 告警与复核、§14 页面组织
**约束参考**：§9.3、§11.3
**设计规范**：`docs/design/`（`DESIGN_BRIEF.md`、`DESIGN_SYSTEM.md`、`INTERACTION_RULES.md`、`VISUAL_QA.md`）；UI 变更前先读，验收按 `VISUAL_QA.md`
**阶段**：1（最小页）/ 阶段 2–5（完整）
**依赖**：30 的 OpenAPI；10 的 WS 信封

## 落点

```text
frontend/src/
├── routes/_layout/
│   ├── index.tsx                     # 工位总览（替换欢迎页）
│   ├── stations.$stationId.tsx       # 工位监控
│   ├── executions.$executionId.tsx   # 执行详情/时间线
│   ├── sops.tsx                      # SOP 列表、校验、发布、只读 DAG
│   ├── alarms.tsx                    # 告警中心
│   └── system.tsx                    # 相机/绑定/模型/采样/运行时
├── features/{stations,executions,alarms,sops,system}/
├── hooks/useExecutionSocket.ts
└── client/                           # 仅生成，禁止手改
```

## 页面（基线 §14）

| 页面 | 阶段 1 最小集 | 后续 |
|---|---|---|
| 工位总览 | 工位状态、活动执行、未处理告警、相机/Runtime 健康 | 批量视图 |
| 工位监控 | 当前 SOP 步骤、最近事件、健康状态 | 实时预览、证据入口 |
| SOP 管理 | 列表、校验结果、发布、版本历史、只读依赖展示 | DAG 可视化编辑 |
| 执行历史 | 时间线、每步结果、来源事件、规则/模型版本、证据状态 | 证据回放 |
| 告警中心 | 分类/严重度/状态筛选、确认/关闭 | 升级与批量处理 |
| 系统配置 | 相机与绑定只读或表单 | 模型、采样策略、运行时注册 |

## 约束

- 判定逻辑一律来自后端；前端只呈现步骤状态、`reason_code` 与告警，不推导最终结论。
- 实时预览与证据回放是两条路径（基线 §11.3）：预览失败不影响证据；预览流不作为证据存档。
- WS 只用于刷新：退避重连，重连后走 REST 拉权威快照；`message_id` 去重。
- 每个请求有 loading / error / empty 三态；Runtime 不可用时仍显示设备故障，不伪装成无事件。
- 告警展示必须区分 `PROCESS_COMPLIANCE` 与系统健康类；不得把置信度显示为“合格率”。
- 人工复核界面记录决定、理由，并保留原始模型输出与证据引用。

## 测试

- 保留并更新 `frontend/tests/home.spec.ts`；
- 新增：总览渲染、告警筛选与确认、执行时间线、WS 断线恢复、预览失败但状态仍显示。

## DoD

`bun run lint`、`bun run build`、`bunx playwright test` 通过；`scripts/generate-client.sh` 后无未提交 diff。
