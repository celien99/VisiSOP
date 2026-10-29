import type { SopVersionRead } from "@/client"
import { formatDuration } from "@/lib/format"

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function stepDetail(dsl: Record<string, unknown>, key: string) {
  const steps = Array.isArray(dsl.steps) ? dsl.steps : []
  for (const raw of steps) {
    if (!isRecord(raw) || raw.key !== key) continue
    const timeout =
      typeof raw.timeout_ms === "number" ? formatDuration(raw.timeout_ms) : "—"
    const evidence =
      isRecord(raw.evidence) && raw.evidence.required === true
        ? `必需${typeof raw.evidence.kind === "string" ? `（${raw.evidence.kind}）` : ""}`
        : "非必需"
    return { evidence, timeout }
  }
  return { evidence: "—", timeout: "—" }
}

// Read-only by design: stage 1 validates and publishes, it does not edit a DAG.
export function SopDag({ version }: { version: SopVersionRead }) {
  return (
    <ol className="vs-dag">
      {version.steps.map((step) => {
        const detail = stepDetail(version.dsl, step.key)
        return (
          <li className="vs-dag__item" key={step.key}>
            <span className="vs-dag__key">{step.key}</span>
            <span className="vs-dag__body">
              <span className="vs-row__main">{step.name}</span>
              <span className="vs-row__meta">
                {step.type} · 超时 {detail.timeout} · 证据 {detail.evidence}
              </span>
              <span className="vs-row__meta">
                {step.depends_on.length > 0
                  ? `依赖：${step.depends_on.join("、")}`
                  : "起点"}
              </span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
