import type { ReactNode } from "react"

// Outline status chip: colour + text. Never colour alone (DESIGN_SYSTEM §5.7).
export function StatusChip({
  color,
  children,
}: {
  color: string
  children: ReactNode
}) {
  return (
    <span className="vs-status-chip" style={{ borderColor: color }}>
      <span
        aria-hidden="true"
        className="vs-status-chip__dot"
        style={{ background: color }}
      />
      {children}
    </span>
  )
}
