import { useEffect, useRef, useState } from "react"
import { apiUrl } from "@/lib/api"

export type SocketStatus = "CONNECTING" | "OPEN" | "CLOSED"

// The socket is a refetch hint, never a data channel: payloads are ignored
// beyond their type, and REST stays authoritative.
const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000, 30000]
const SEEN_LIMIT = 100

function socketUrl(): string {
  const url = new URL(apiUrl("/api/ws"), window.location.href)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}

export function useExecutionSocket(onMessage?: (type: string) => void) {
  const [status, setStatus] = useState<SocketStatus>("CONNECTING")
  const [lastMessageAt, setLastMessageAt] = useState<Date | null>(null)
  const handler = useRef(onMessage)

  useEffect(() => {
    handler.current = onMessage
  }, [onMessage])

  useEffect(() => {
    const seen = new Set<string>()
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let attempt = 0
    let stopped = false

    const connect = () => {
      setStatus("CONNECTING")
      socket = new WebSocket(socketUrl())

      socket.onopen = () => {
        attempt = 0
        setStatus("OPEN")
      }

      socket.onmessage = (event) => {
        let frame: { message_id?: unknown; type?: unknown }
        try {
          frame = JSON.parse(String(event.data))
        } catch {
          return
        }
        const id =
          typeof frame.message_id === "string" ? frame.message_id : null
        if (id) {
          if (seen.has(id)) return
          seen.add(id)
          if (seen.size > SEEN_LIMIT) {
            const oldest = seen.values().next().value
            if (oldest) seen.delete(oldest)
          }
        }
        setLastMessageAt(new Date())
        if (typeof frame.type === "string") handler.current?.(frame.type)
      }

      socket.onclose = () => {
        if (stopped) return
        setStatus("CLOSED")
        const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
        attempt += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }

      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      stopped = true
      window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return { status, lastMessageAt }
}
