import type { StationRuntimeStateRead } from "@/client"
import { elapsedSince } from "@/lib/format"
import { PROCESS_STATUS_LABEL } from "@/lib/status"

type AttentionStripProps = {
  states: StationRuntimeStateRead[]
  serverTime: string | null
}

export function AttentionStrip({ states, serverTime }: AttentionStripProps) {
  const rows = states
    .filter(
      (state) =>
        state.process_status === "REVIEW" || state.process_status === "ALARM",
    )
    .sort((a, b) =>
      (a.attention_since ?? "").localeCompare(b.attention_since ?? ""),
    )

  return (
    <section
      aria-label="待处置机位"
      className="vs-attention"
      data-testid="attention-strip"
    >
      <p className="vs-attention__title">待处置 · {rows.length} 机位</p>
      {rows.length === 0 ? (
        <p className="vs-attention__item">当前无待处置机位</p>
      ) : (
        rows.map((state) => (
          <p className="vs-attention__item" key={state.station.id}>
            <strong>{state.station.code}</strong>{" "}
            {PROCESS_STATUS_LABEL[state.process_status] ?? state.process_status}
            {state.attention_since && serverTime
              ? ` · 已等 ${elapsedSince(state.attention_since, serverTime)}`
              : null}
          </p>
        ))
      )}
    </section>
  )
}
