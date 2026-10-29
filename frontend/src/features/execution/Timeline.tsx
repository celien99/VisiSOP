import type { TimelineItemRead } from "@/client"
import { formatDateTime } from "@/lib/format"
import { REASON_CODE_LABEL } from "@/lib/status"

const TYPE_LABEL: Record<string, string> = {
  EVENT: "事件",
  STEP: "步骤",
  ALARM: "告警",
}

export function Timeline({ items }: { items: TimelineItemRead[] }) {
  if (items.length === 0) {
    return <p className="vs-empty">暂无时间线记录</p>
  }
  return (
    <ol className="vs-timeline">
      {items.map((item, index) => (
        <li
          className="vs-timeline__item"
          key={`${item.type}-${item.at}-${index}`}
        >
          <span className="vs-timeline__time">{formatDateTime(item.at)}</span>
          <span className="vs-timeline__type">
            {TYPE_LABEL[item.type] ?? item.type}
          </span>
          <span className="vs-timeline__body">
            <span className="vs-row__main">{item.title}</span>
            {item.detail ? (
              <span className="vs-row__meta">{item.detail}</span>
            ) : null}
            <span className="vs-row__meta">
              {item.event_type ? `${item.event_type} · ` : ""}
              {item.confidence !== null
                ? `置信度 ${item.confidence.toFixed(2)} · `
                : ""}
              {item.model ? `模型 ${item.model} · ` : ""}
              {item.reason_code
                ? (REASON_CODE_LABEL[item.reason_code] ?? item.reason_code)
                : ""}
            </span>
          </span>
        </li>
      ))}
    </ol>
  )
}
