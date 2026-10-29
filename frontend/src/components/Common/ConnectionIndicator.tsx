import type { SocketStatus } from "@/hooks/useExecutionSocket"

const LABEL: Record<SocketStatus, string> = {
  OPEN: "已连接",
  CONNECTING: "连接中",
  CLOSED: "连接中断",
}

type ConnectionIndicatorProps = {
  status: SocketStatus
  lastMessageAt: Date | null
}

export function ConnectionIndicator({
  status,
  lastMessageAt,
}: ConnectionIndicatorProps) {
  return (
    <span
      aria-live="polite"
      className="vs-conn"
      data-testid="connection-indicator"
      title="推送只提示刷新；页面数据始终来自 REST 快照"
    >
      <span
        aria-hidden="true"
        className="vs-conn__dot"
        data-live={status === "OPEN"}
      />
      {LABEL[status]}
      {lastMessageAt ? (
        <span className="vs-conn__time">
          {lastMessageAt.toLocaleTimeString("zh-CN", { hour12: false })}
        </span>
      ) : null}
    </span>
  )
}
