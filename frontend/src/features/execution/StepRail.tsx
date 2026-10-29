import type { StepSummaryRead } from "@/client"
import { STEP_STATUS_COLOR, STEP_STATUS_LABEL } from "@/lib/status"

type StepRailProps = {
  steps: StepSummaryRead[]
  compact?: boolean
}

// The only "how far along" expression: one segment per backend step, no
// percentage. Segment 17×5px is fixed by DESIGN_SYSTEM §5.4.
export function StepRail({ steps, compact = false }: StepRailProps) {
  if (steps.length === 0) return null
  const activeIndex = steps.findIndex(
    (step) => step.status === "ACTIVE" || step.status === "NEEDS_REVIEW",
  )
  const position =
    activeIndex >= 0
      ? activeIndex + 1
      : steps.filter((step) => step.status === "COMPLETED").length

  return (
    <div className="vs-rail" data-compact={compact || undefined}>
      {steps.map((step) => (
        <span
          aria-label={`${step.name} ${STEP_STATUS_LABEL[step.status] ?? step.status}`}
          className="vs-rail__seg"
          key={step.key}
          role="img"
          style={{
            background: STEP_STATUS_COLOR[step.status] ?? "var(--vs-off)",
          }}
        />
      ))}
      <span className="vs-rail__count">
        {position} / {steps.length}
      </span>
    </div>
  )
}
