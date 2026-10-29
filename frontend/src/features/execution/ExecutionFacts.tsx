import type {
  EvidenceRead,
  ExecutionDetailRead,
  StationRuntimeStateRead,
} from "@/client"
import { StatusChip } from "@/components/Common/StatusChip"
import { formatDateTime, formatTime } from "@/lib/format"
import {
  EXECUTION_STATUS_LABEL,
  HEALTH_LABEL,
  REASON_CODE_LABEL,
  STEP_STATUS_COLOR,
  STEP_STATUS_LABEL,
} from "@/lib/status"

const EVIDENCE_LABEL: Record<string, string> = {
  AVAILABLE: "可用",
  PENDING_VERIFY: "待校验",
  MISSING: "缺失",
}

type ExecutionFactsProps = {
  execution: ExecutionDetailRead | null
  system: StationRuntimeStateRead | null
  dense?: boolean
  onOpenEvidence?: (evidence: EvidenceRead) => void
}

// Four facts, four blocks. They are never merged into one verdict: visual
// observation, process compliance, system health and evidence availability
// each keep their own source (DESIGN_BRIEF §4).
export function ExecutionFacts({
  execution,
  system,
  dense = false,
  onOpenEvidence,
}: ExecutionFactsProps) {
  const steps = execution?.steps ?? []
  const events = steps.flatMap((step) =>
    step.matched_events.map((event) => ({ ...event, stepKey: step.key })),
  )
  const evidence = steps.flatMap((step) => step.evidence)

  return (
    <div className="vs-facts-grid" data-dense={dense || undefined}>
      <section className="vs-panel" data-testid="fact-visual">
        <h2 className="vs-panel__title">视觉</h2>
        <p className="vs-panel__hint">模型原始输出，不直接等于判定</p>
        {events.length === 0 ? (
          <p className="vs-empty">暂无视觉事件</p>
        ) : (
          <ul className="vs-rows">
            {events.map((event) => (
              <li className="vs-row" key={event.event_id}>
                <span className="vs-row__main">{event.event_type}</span>
                <span className="vs-row__meta">
                  置信度 {event.confidence.toFixed(2)} · {event.camera_id} ·{" "}
                  {formatTime(event.occurred_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="vs-panel" data-testid="fact-process">
        <h2 className="vs-panel__title">工艺</h2>
        {execution ? (
          <p className="vs-panel__hint">
            SOP-{execution.sop_key} v{execution.sop_version} · sha256:
            {execution.sop_content_hash.slice(0, 8)}… ·{" "}
            {EXECUTION_STATUS_LABEL[execution.status] ?? execution.status}
          </p>
        ) : (
          <p className="vs-panel__hint">暂无执行</p>
        )}
        {steps.length > 0 ? (
          <ul className="vs-rows">
            {steps.map((step) => (
              <li className="vs-row" key={step.key}>
                <span className="vs-row__main">
                  <StatusChip
                    color={STEP_STATUS_COLOR[step.status] ?? "var(--vs-off)"}
                  >
                    {STEP_STATUS_LABEL[step.status] ?? step.status}
                  </StatusChip>{" "}
                  {step.name}
                </span>
                <span className="vs-row__meta">
                  {step.reason_code
                    ? (REASON_CODE_LABEL[step.reason_code] ?? step.reason_code)
                    : "—"}
                  {step.deadline_at
                    ? ` · 截止 ${formatDateTime(step.deadline_at)}`
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="vs-panel" data-testid="fact-system">
        <h2 className="vs-panel__title">系统</h2>
        {system ? (
          <ul className="vs-rows">
            <li className="vs-row">
              <span className="vs-row__main">
                {system.camera
                  ? `${system.camera.code} ${system.camera.name}`
                  : "没有绑定相机"}
              </span>
              <span className="vs-row__meta">
                {HEALTH_LABEL[system.camera?.health ?? system.health] ??
                  system.camera?.health ??
                  system.health}
                {system.last_frame_at
                  ? ` · 最后画面 ${formatTime(system.last_frame_at)}`
                  : " · 无帧时间"}
              </span>
            </li>
            <li className="vs-row">
              <span className="vs-row__main">
                {system.preview_url ? "预览已配置" : "预览未接入"}
              </span>
              <span className="vs-row__meta">预览不是证据</span>
            </li>
          </ul>
        ) : (
          <p className="vs-empty">系统状态不可用</p>
        )}
      </section>

      <section className="vs-panel" data-testid="fact-evidence">
        <h2 className="vs-panel__title">证据</h2>
        <p className="vs-panel__hint">只有「可用」的证据可以打开</p>
        {evidence.length === 0 ? (
          <p className="vs-empty">无证据</p>
        ) : (
          <ul className="vs-evidence">
            {evidence.map((asset) => {
              const available = asset.status === "AVAILABLE"
              return (
                <li key={asset.id}>
                  <button
                    aria-disabled={!available}
                    className="vs-evidence__thumb"
                    data-testid="evidence-thumb"
                    disabled={!available}
                    onClick={() => available && onOpenEvidence?.(asset)}
                    type="button"
                  >
                    <span>{EVIDENCE_LABEL[asset.status] ?? "不可用"}</span>
                    <span className="vs-row__meta">{asset.event_id}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
