const pad = (value: number) => String(value).padStart(2, "0")

export function formatTime(value: string | Date): string {
  const date = new Date(value)
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function formatDateTime(value: string | Date): string {
  const date = new Date(value)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${formatTime(date)}`
}

export function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} 分 ${pad(seconds % 60)} 秒`
  return `${Math.floor(minutes / 60)} 小时 ${pad(minutes % 60)} 分`
}

// Wait time is measured against the server's own clock, not the browser's.
export function elapsedSince(since: string, serverTime: string): string {
  return formatDuration(
    new Date(serverTime).getTime() - new Date(since).getTime(),
  )
}
