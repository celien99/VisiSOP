import { useState } from "react"
import { formatTime } from "@/lib/format"

type PreviewPanelProps = {
  previewUrl: string | null
  snapshotUrl: string | null
  health: string
  lastFrameAt: string | null
  alt: string
}

type PreviewState =
  | "live"
  | "loading"
  | "last-frame"
  | "unavailable"
  | "no-signal"
  | "missing"

// A preview is never evidence. Each non-live state is named so a stale frame
// can never pass as a live stream (INTERACTION_RULES §2.3).
export function PreviewPanel({
  previewUrl,
  snapshotUrl,
  health,
  lastFrameAt,
  alt,
}: PreviewPanelProps) {
  const [failed, setFailed] = useState(false)
  const [snapshotFailed, setSnapshotFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)

  let state: PreviewState
  if (health === "UNAVAILABLE") state = "no-signal"
  else if (!previewUrl) state = "missing"
  else if (!failed) state = loaded ? "live" : "loading"
  else if (snapshotUrl && !snapshotFailed) state = "last-frame"
  else state = "unavailable"

  if (state === "no-signal") {
    return (
      <div className="vs-preview vs-preview--offline">
        <span>无信号 · 没有画面信号</span>
        {lastFrameAt ? (
          <span className="vs-preview__stamp">
            最后 {formatTime(lastFrameAt)}
          </span>
        ) : null}
      </div>
    )
  }

  if (state === "unavailable") {
    return (
      <div className="vs-preview vs-preview--empty">
        <span>预览不可用</span>
        {lastFrameAt ? (
          <span className="vs-preview__stamp">
            最后 {formatTime(lastFrameAt)}
          </span>
        ) : null}
      </div>
    )
  }

  if (state === "missing") {
    return (
      <div className="vs-preview vs-preview--empty">
        <span>预览未配置</span>
      </div>
    )
  }

  return (
    <div className="vs-preview">
      <img
        alt={alt}
        onError={() => {
          if (state === "last-frame") setSnapshotFailed(true)
          else setFailed(true)
        }}
        onLoad={() => setLoaded(true)}
        src={
          state === "last-frame"
            ? (snapshotUrl ?? undefined)
            : (previewUrl ?? undefined)
        }
      />
      <span className="vs-preview__note">
        <span>{state === "last-frame" ? "最后一帧" : "实时预览"}</span>
        {state === "last-frame" && lastFrameAt ? (
          <span>{formatTime(lastFrameAt)}</span>
        ) : null}
      </span>
    </div>
  )
}
