// Display maps only: wire values come from the backend and are never invented
// here. Labels follow docs/design/DESIGN_SYSTEM.md §3.3.
export const STEP_STATUS_LABEL: Record<string, string> = {
  PENDING: "未开始",
  ACTIVE: "进行中",
  COMPLETED: "已完成",
  FAILED: "失败",
  SKIPPED: "已跳过",
  TIMED_OUT: "超时",
  NEEDS_REVIEW: "待复核",
}

export const STEP_STATUS_COLOR: Record<string, string> = {
  PENDING: "var(--vs-off)",
  ACTIVE: "var(--vs-ink)",
  COMPLETED: "var(--vs-ok)",
  FAILED: "var(--vs-crit)",
  SKIPPED: "var(--vs-off)",
  TIMED_OUT: "var(--vs-crit)",
  NEEDS_REVIEW: "var(--vs-warn)",
}

export const EXECUTION_STATUS_LABEL: Record<string, string> = {
  CREATED: "已创建",
  RUNNING: "执行中",
  PAUSED: "已暂停",
  COMPLETED: "已完成",
  ABORTED: "已中止",
  NEEDS_REVIEW: "待复核",
}

export const EXECUTION_STATUS_COLOR: Record<string, string> = {
  CREATED: "var(--vs-off)",
  RUNNING: "var(--vs-ink)",
  PAUSED: "var(--vs-warn)",
  COMPLETED: "var(--vs-ok)",
  ABORTED: "var(--vs-off)",
  NEEDS_REVIEW: "var(--vs-warn)",
}

export const PROCESS_STATUS_LABEL: Record<string, string> = {
  IDLE: "空闲",
  RUNNING: "执行中",
  REVIEW: "待复核",
  ALARM: "告警",
  COMPLETED: "已完成",
  OFFLINE: "离线",
}

export const PROCESS_STATUS_COLOR: Record<string, string> = {
  IDLE: "var(--vs-off)",
  RUNNING: "var(--vs-ink)",
  REVIEW: "var(--vs-warn)",
  ALARM: "var(--vs-crit)",
  COMPLETED: "var(--vs-ok)",
  OFFLINE: "var(--vs-off)",
}

export const HEALTH_LABEL: Record<string, string> = {
  HEALTHY: "在线",
  DEGRADED: "降级",
  UNAVAILABLE: "不可用",
  UNKNOWN: "未知",
  STARTING: "启动中",
  STOPPED: "已停止",
  MISCONFIGURED: "配置错误",
}

export const REASON_CODE_LABEL: Record<string, string> = {
  EXECUTION_AMBIGUOUS: "执行歧义",
  LOW_CONFIDENCE: "置信度不足",
  EVIDENCE_MISSING: "证据缺失",
  CAMERA_CONFLICT: "相机冲突",
  LATE_EVENT: "迟到事件",
  MODEL_VERSION_MISMATCH: "模型版本不匹配",
  RULE_VERSION_MISMATCH: "规则版本不匹配",
  MANUAL_SKIP: "人工跳过",
  TIMEOUT: "超时",
  UNEXPECTED_STEP: "意外步骤",
  OUT_OF_ORDER: "顺序错误",
  AUTO_SKIP: "自动跳过",
}

export const ALARM_STATUS_LABEL: Record<string, string> = {
  OPEN: "未处理",
  ACKNOWLEDGED: "已确认",
  RESOLVED: "已解决",
}

export const ALARM_SEVERITY_LABEL: Record<string, string> = {
  LOW: "低",
  MEDIUM: "中",
  HIGH: "高",
  CRITICAL: "严重",
}

export const ALARM_SEVERITY_COLOR: Record<string, string> = {
  LOW: "var(--vs-off)",
  MEDIUM: "var(--vs-warn)",
  HIGH: "var(--vs-crit)",
  CRITICAL: "var(--vs-crit)",
}

export const ALARM_CATEGORY_LABEL: Record<string, string> = {
  PROCESS_COMPLIANCE: "工艺合规",
  VISION_QUALITY: "视觉质量",
  DEVICE_HEALTH: "设备健康",
  DATA_INTEGRITY: "数据完整性",
  SYSTEM: "系统",
}

export const EVIDENCE_STATUS_LABEL: Record<string, string> = {
  AVAILABLE: "可用",
  PENDING_VERIFY: "待校验",
  MISSING: "缺失",
}
