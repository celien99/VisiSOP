# AGENTS.md — VisiSOP 项目级约束

本文件是任何开发或设计 Agent 的入口，不是 `CLAUDE.md` 的副本。`CLAUDE.md` 仍是仓库操作指南；两者冲突时以 `CLAUDE.md` 为准。系统行为以 `docs/AI_SOP_Platform_Architecture_v2.0.md` 为准，严格不变量以 `docs/AI_SOP_Architecture_Design_v1.1.md` 为准，前端视觉与交互以 `docs/design/` 为准，实现落点以 `docs/implementation/` 为准。

## 1. 先读顺序

1. `CLAUDE.md`
2. `docs/design/DESIGN_BRIEF.md`
3. `docs/design/DESIGN_SYSTEM.md`
4. `docs/design/INTERACTION_RULES.md`
5. `docs/design/VISUAL_QA.md`
6. `docs/implementation/README.md` 与本工作包简报（前端为 `40-frontend.md`）
7. 该工作包要求的架构基线章节

不要从组件开始，从规则开始。先确认这条界面在回答谁的什么问题，再决定它长什么样。

### 1.1 目录映射

需求里的 `project/src/...` 是通用示意；本仓库的实际落点：

| 通用结构 | 本仓库 |
|---|---|
| `docs/design/` | `docs/design/` |
| `src/styles/tokens.css` | `frontend/src/styles/tokens.css` |
| `src/components/` | `frontend/src/components/`（共享 UI） |
| `src/features/` | `frontend/src/features/{wall,analytics,stations,executions,records,sops,system}/`（实现时创建） |
| `src/layouts/` | 暂无独立目录；应用壳是 `frontend/src/routes/_layout.tsx`，需要时再抽 |
| 页面 | `frontend/src/routes/_layout/`（TanStack Router 文件路由） |

不要为了“结构完整”创建空目录或 `.gitkeep`；目录在第一个真实文件出现时创建。

## 2. 不可协商的产品约束

- **四类事实不得合并**：视觉事实、工艺事实、系统事实、证据事实各自有来源、各自呈现。禁止做一个“总状态”把冲突抹平。
- **判定只来自后端**：前端只呈现步骤状态、`reason_code`、告警与证据引用，不推导 SOP 结论，不解析 SOP DSL，不在前端计算“是否合规”。
- **实时预览不是证据**：预览与证据回放是两条路径。预览失败不得隐藏设备健康；预览流不得进入证据查看器，也不得被截图当作证据。
- **`NEEDS_REVIEW` 是一等结果**：不是错误回收站，不得用红色错误样式；`FAILED`、`TIMED_OUT`、`SKIPPED` 也必须彼此可辨。
- **工艺合规与系统健康必须分开展示**：`PROCESS_COMPLIANCE` 不得和 `DEVICE_HEALTH` / `INFERENCE_HEALTH` / `PLATFORM_HEALTH` 混成一个告警列表或一个总数。
- **WS 只负责刷新**：WebSocket 推送状态变化、告警、健康；REST 快照是权威来源。断线重连后必须重新拉快照，`message_id` 去重，不得把旧快照标成“实时”。
- **证据可用性必须可见**：只有 `AVAILABLE` 才算可用；`PENDING_VERIFY`、缺失、校验失败都要明确显示为不可用，不能用占位图或预览帧补位。
- **置信度不是合格率**：显示 `0.71` 与阈值 `0.92` 及模型版本，不得写成 `71% 合格率`，也不得用置信度推导通过/不通过。
- **阶段边界**：阶段 1 没有真实相机、实时预览、DeepStream/Osprey、图形化 SOP 编辑器；不要为这些未交付能力做“看起来能用”的假界面。

## 3. 前端实现约束

- API 只走 `src/client` 的生成客户端；不得手改 `src/client/**`，不得绕开它直接 `fetch`/`axios`。
- 服务端数据只放在 TanStack Query；不复制到全局 store。选择、筛选、时间窗口放 URL 或局部状态。
- 每个请求有 loading / error / empty 三态；局部失败只影响局部面板，不得让整页空白。Runtime 不可用时仍显示设备故障，不伪装成“无事件”。
- 不得用 `any`、类型断言或手写枚举字符串绕过生成类型；wire value 以契约为准。
- 颜色、字体、间距、圆角、动效只能来自 `frontend/src/styles/tokens.css` 的 `--vs-*`；组件里不写十六进制、不写魔法像素。
- 一个屏幕一个主体。监控墙的主体是画面，看板的主体是时间曲线，详情的主体是证据。禁止把内容切成等宽圆角卡片、禁止通用阴影/渐变/毛玻璃/伪 3D；分隔用 1px 结构线，层级靠底色与留白。
- 界面是暗场控制台：石墨底 + 骨白字。不做浅色主题，也不做半套主题。
- 信号色只表示状态（绿=正常/完成，琥珀=待确认/等待，红=工艺异常，灰=离线）；品牌、导航、标题装饰不得使用信号色。状态必须同时有图标或文字，不得只靠颜色。图表单轴单色相（`--vs-series`），状态色不得用作数据系列。
- 生产代码不得出现通过率、合格率、效率分或综合评分；前端也不得自行计算看板聚合指标。
- 中文界面，英文只用于 wire value、ID、时间戳、哈希和机器事实。状态文案使用 `DESIGN_SYSTEM.md` §3.3 的映射，不自创译名。
- 生产代码不得出现假数据、假指标、假哈希、假工位名；夹具只存在于测试或设计稿，演示数据必须标注"演示模式"。
- 键盘可达：可见 focus、跳过导航、`Esc` 关闭、面板关闭后焦点回到触发点；监控墙支持方向键走格；尊重 `prefers-reduced-motion`。

## 4. 改哪里

| 变更 | 应改 |
|---|---|
| 颜色、字体、间距、组件形态 | `frontend/src/styles/tokens.css` + `docs/design/DESIGN_SYSTEM.md` |
| 关键交互、状态规则、错误/空态 | `docs/design/INTERACTION_RULES.md` |
| 产品定位、页面地图、视觉方向 | `docs/design/DESIGN_BRIEF.md` |
| 视觉验收标准 | `docs/design/VISUAL_QA.md` |
| 系统行为、状态机、证据语义、API | 架构基线 / 约束参考 / ADR；不要只改设计文档 |

设计规则与架构冲突时，停下来写 ADR，不得静默选边。改了一条规则，就在同一个 PR 里更新对应文档和验收项；文档漂移比没有文档更糟。

## 5. UI 改造顺序

1. 读本文与 `DESIGN_BRIEF.md`，确认页面主体和用户问题。
2. 在 `VISUAL_QA.md` 里找到该页的验收项。
3. 只改一个有代表性的页面；用现有组件和 `--vs-*` token，不新建组件库。
4. 补齐 loading / error / empty / stale / 证据不可用等状态。
5. 在 1440×900、1600×1000、1920×1080 下做视觉验收；需要时补 Playwright。
6. 汇报真实命令输出与截图路径；不要用“应该没问题”代替验证。
7. 验收通过后，再把确认的规则扩展到其他页面。

不要一次重做六个页面。先用一页证明方向，再复制规则。

## 6. 完成定义

- `cd frontend && bun run lint`、`bun run build`、`bunx playwright test` 通过（以 `docs/implementation/40-frontend.md` 为准）。
- 运行 `bash ./scripts/generate-client.sh` 后没有未提交 diff。
- `VISUAL_QA.md` 的必检项有结果；关键页面有 1600×1000 截图。
- 无控制台错误、无死链、无假数据、无未处理的空/错/断线状态。
- 键盘、对比度、reduced motion 实际检查过，不是“理论上支持”。

## 7. 硬性禁止

- 不得把四类事实合成一个状态，或用前端逻辑补出后端没有的结论。
- 不得把置信度写成合格率，或把预览当作证据。
- 不得把 `PENDING_VERIFY` 显示为可用证据。
- 不得因为预览失败而隐藏设备/推理/平台故障。
- 不得新增第三套设计系统、第二个 UI 组件库或另一套颜色 token；`--vs-*` 是唯一目标，shadcn 的 `--*` 只是迁移前的遗留层。
- 不得手改生成客户端，或把生成文件当作手写代码修。
- 不得为未确认的语义（复核结果集、原因码、工位绑定）自造字段；等契约或 ADR。
- 不得把设计稿里的示意元素（假工位名、假哈希、示意 ROI、第二视角占位）直接搬进生产。
