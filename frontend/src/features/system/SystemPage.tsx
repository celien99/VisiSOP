import { useQuery } from "@tanstack/react-query"
import { HealthService } from "@/client"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDateTime, formatTime } from "@/lib/format"
import { queryKeys } from "@/lib/queryKeys"
import { HEALTH_LABEL } from "@/lib/status"

const STALE_AFTER_MS = 15000

export function SystemPage() {
  const healthQuery = useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => {
      const response = await HealthService.getHealthSummary()
      return response.data
    },
    refetchInterval: 5000,
  })
  const summary = healthQuery.data

  return (
    <div className="vs-page">
      <p className="vs-page__code">SYSTEM / 系统</p>
      <h1 className="vs-page__title">系统健康</h1>
      <p className="vs-page__lede">
        相机、运行时与平台的健康是系统事实，与工艺判定分开呈现。
      </p>

      {healthQuery.isPending ? <div className="vs-skeleton-card" /> : null}
      {healthQuery.isError ? (
        <div className="vs-panel" role="alert">
          <p>系统健康加载失败。</p>
          <button
            className="vs-chip vs-focus"
            onClick={() => void healthQuery.refetch()}
            type="button"
          >
            重试
          </button>
        </div>
      ) : null}

      {summary ? (
        <>
          <section
            className="vs-panel vs-system-health"
            data-testid="system-health"
          >
            <h2 className="vs-panel__title">平台</h2>
            <ul className="vs-rows">
              <li className="vs-row">
                <span className="vs-row__main">
                  数据库 · {HEALTH_LABEL[summary.database] ?? summary.database}
                </span>
                <span className="vs-row__meta">
                  快照 {formatTime(summary.server_time)}
                </span>
              </li>
            </ul>
          </section>

          <section className="vs-panel vs-system-health">
            <h2 className="vs-panel__title">运行时</h2>
            {summary.runtimes.length === 0 ? (
              <p className="vs-empty">暂无注册运行时。</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>运行时</TableHead>
                    <TableHead>版本</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>最后心跳</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.runtimes.map((runtime) => {
                    const stale =
                      runtime.last_heartbeat_at !== null &&
                      new Date(summary.server_time).getTime() -
                        new Date(runtime.last_heartbeat_at).getTime() >
                        STALE_AFTER_MS
                    return (
                      <TableRow key={runtime.runtime_id}>
                        <TableCell>{runtime.runtime_id}</TableCell>
                        <TableCell>{runtime.version}</TableCell>
                        <TableCell>
                          {HEALTH_LABEL[runtime.status] ?? runtime.status}
                        </TableCell>
                        <TableCell>
                          {runtime.last_heartbeat_at
                            ? formatDateTime(runtime.last_heartbeat_at)
                            : "—"}
                          {stale ? " · 心跳超时" : ""}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </section>

          <section className="vs-panel vs-system-health">
            <h2 className="vs-panel__title">相机</h2>
            {summary.cameras.length === 0 ? (
              <p className="vs-empty">暂无相机。</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>相机</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>最后画面</TableHead>
                    <TableHead>预览</TableHead>
                    <TableHead>快照</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.cameras.map((camera) => (
                    <TableRow key={camera.id}>
                      <TableCell>
                        {camera.code} {camera.name}
                      </TableCell>
                      <TableCell>
                        {HEALTH_LABEL[camera.health] ?? camera.health}
                      </TableCell>
                      <TableCell>
                        {camera.last_frame_at
                          ? formatTime(camera.last_frame_at)
                          : "—"}
                      </TableCell>
                      <TableCell>
                        {camera.preview_url ? (
                          <a
                            className="vs-utility"
                            href={camera.preview_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            预览流
                          </a>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell>
                        {camera.snapshot_url ? (
                          <a
                            className="vs-utility"
                            href={camera.snapshot_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            快照
                          </a>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}
