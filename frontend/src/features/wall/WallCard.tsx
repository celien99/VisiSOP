import { Link } from "@tanstack/react-router"
import type { StationRuntimeStateRead } from "@/client"
import { StepRail } from "@/features/execution/StepRail"
import { formatTime, isStale } from "@/lib/format"
import {
  PROCESS_STATUS_COLOR,
  PROCESS_STATUS_LABEL,
  STEP_STATUS_LABEL,
} from "@/lib/status"
import { PreviewPanel } from "./PreviewPanel"

type WallCardProps = {
  state: StationRuntimeStateRead
  focused?: boolean
}

export function WallCard({ state, focused = false }: WallCardProps) {
  const { station, camera, execution } = state
  const offline = !camera || camera.health === "UNAVAILABLE"
  const status = offline ? "OFFLINE" : state.process_status
  const color = PROCESS_STATUS_COLOR[status] ?? "var(--vs-off)"
  const stepName = execution?.current_step_name ?? "暂无进行中的执行"
  const stepStatus = execution?.current_step_status

  return (
    <Link
      className="vs-tile"
      data-focused={focused || undefined}
      data-testid="wall-card"
      id={`tile-${station.id}`}
      params={{ stationId: station.id }}
      to="/stations/$stationId"
    >
      <div className="vs-tile__head">
        <span className="vs-tile__code">{station.code}</span>
        <span className="vs-tile__name">{station.name}</span>
        <span className="vs-status-chip" style={{ borderColor: color }}>
          <span
            aria-hidden="true"
            className="vs-status-chip__dot"
            style={{ background: color }}
          />
          {PROCESS_STATUS_LABEL[status] ?? status}
        </span>
      </div>

      <PreviewPanel
        alt={`${station.code} ${station.name} 画面`}
        health={camera?.health ?? "UNAVAILABLE"}
        key={`${state.preview_url ?? ""}|${camera?.health ?? ""}`}
        lastFrameAt={state.last_frame_at}
        previewUrl={state.preview_url}
        snapshotUrl={state.snapshot_url}
        stale={isStale(state.last_frame_at, state.server_time)}
      />

      <div className="vs-tile__foot">
        <StepRail compact steps={state.steps} />
        <p className="vs-tile__step">{stepName}</p>
        <p className="vs-tile__meta">
          <span>
            {stepStatus ? (STEP_STATUS_LABEL[stepStatus] ?? stepStatus) : "—"}
          </span>
          <span>告警 {state.open_alarm_count}</span>
          <span>
            {state.last_frame_at ? formatTime(state.last_frame_at) : "无帧时间"}
          </span>
        </p>
      </div>
    </Link>
  )
}
