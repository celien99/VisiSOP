import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { AlarmsService, ExecutionsService } from "@/client"
import { StatusChip } from "@/components/Common/StatusChip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatDateTime, formatTime } from "@/lib/format"
import { queryKeys } from "@/lib/queryKeys"
import {
  ALARM_CATEGORY_LABEL,
  ALARM_SEVERITY_COLOR,
  ALARM_SEVERITY_LABEL,
  ALARM_STATUS_LABEL,
  EXECUTION_STATUS_COLOR,
  EXECUTION_STATUS_LABEL,
  REASON_CODE_LABEL,
} from "@/lib/status"

export type RecordsSearch = {
  tab?: "alarms"
  status?: string
  station_id?: string
}

type RecordsPageProps = {
  search: RecordsSearch
  onSearchChange: (patch: Partial<RecordsSearch>) => void
}

const EXECUTION_FILTERS = [
  "RUNNING",
  "PAUSED",
  "NEEDS_REVIEW",
  "COMPLETED",
  "ABORTED",
] as const
const ALARM_FILTERS = ["OPEN", "ACKNOWLEDGED", "RESOLVED"] as const

export function RecordsPage({ search, onSearchChange }: RecordsPageProps) {
  const tab = search.tab === "alarms" ? "alarms" : "executions"
  const executionStatus = EXECUTION_FILTERS.find(
    (value) => value === search.status,
  )
  const alarmStatus = ALARM_FILTERS.find((value) => value === search.status)
  const filterKey = JSON.stringify(search)

  const executionsQuery = useQuery({
    queryKey: queryKeys.executions(filterKey),
    queryFn: async () => {
      const response = await ExecutionsService.listExecutions({
        query: {
          station_id: search.station_id ?? null,
          status: executionStatus ?? null,
        },
      })
      return response.data
    },
  })

  const alarmsQuery = useQuery({
    queryKey: queryKeys.alarms(filterKey),
    queryFn: async () => {
      const response = await AlarmsService.listAlarms({
        query: {
          station_id: search.station_id ?? null,
          status: alarmStatus ?? null,
        },
      })
      return response.data
    },
  })

  const filters = tab === "alarms" ? ALARM_FILTERS : EXECUTION_FILTERS
  const statusLabel = (value: string) =>
    tab === "alarms"
      ? (ALARM_STATUS_LABEL[value] ?? value)
      : (EXECUTION_STATUS_LABEL[value] ?? value)

  return (
    <div className="vs-page">
      <p className="vs-page__code">RECORDS / 记录</p>
      <h1 className="vs-page__title">记录</h1>

      <Tabs
        onValueChange={(value) =>
          onSearchChange({
            status: undefined,
            tab: value === "alarms" ? "alarms" : undefined,
          })
        }
        value={tab}
      >
        <TabsList>
          <TabsTrigger value="executions">执行</TabsTrigger>
          <TabsTrigger value="alarms">告警</TabsTrigger>
        </TabsList>

        <div className="vs-filterbar vs-record-filters">
          <label className="vs-filterbar__label" htmlFor="record-status">
            状态
          </label>
          <select
            className="vs-select"
            id="record-status"
            onChange={(event) =>
              onSearchChange({ status: event.target.value || undefined })
            }
            value={search.status ?? ""}
          >
            <option value="">全部</option>
            {filters.map((value) => (
              <option key={value} value={value}>
                {statusLabel(value)}
              </option>
            ))}
          </select>

          <label className="vs-filterbar__label" htmlFor="record-station">
            工位
          </label>
          <input
            className="vs-input vs-input--compact"
            defaultValue={search.station_id ?? ""}
            id="record-station"
            onKeyDown={(event) => {
              if (event.key !== "Enter") return
              onSearchChange({
                station_id: event.currentTarget.value || undefined,
              })
            }}
            placeholder="ST-01"
          />
        </div>

        <TabsContent value="executions">
          {executionsQuery.isPending ? (
            <div className="vs-skeleton-card" />
          ) : executionsQuery.isError ? (
            <div className="vs-panel" role="alert">
              <p>执行记录加载失败。</p>
              <button
                className="vs-chip vs-focus"
                onClick={() => void executionsQuery.refetch()}
                type="button"
              >
                重试
              </button>
            </div>
          ) : (executionsQuery.data ?? []).length === 0 ? (
            <p className="vs-empty">当前筛选没有执行记录。清除筛选后再看。</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>开始时间</TableHead>
                  <TableHead>工位</TableHead>
                  <TableHead>SOP</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>当前步骤</TableHead>
                  <TableHead>详情</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(executionsQuery.data ?? []).map((execution) => (
                  <TableRow data-testid="execution-row" key={execution.id}>
                    <TableCell>
                      {formatDateTime(execution.started_at)}
                    </TableCell>
                    <TableCell>{execution.id}</TableCell>
                    <TableCell>
                      SOP-{execution.sop_key} v{execution.sop_version}
                    </TableCell>
                    <TableCell>
                      <StatusChip
                        color={
                          EXECUTION_STATUS_COLOR[execution.status] ??
                          "var(--vs-off)"
                        }
                      >
                        {EXECUTION_STATUS_LABEL[execution.status] ??
                          execution.status}
                      </StatusChip>
                    </TableCell>
                    <TableCell>{execution.current_step_name ?? "—"}</TableCell>
                    <TableCell>
                      <Link
                        className="vs-utility vs-focus"
                        params={{ executionId: execution.id }}
                        to="/executions/$executionId"
                      >
                        打开
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="alarms">
          {alarmsQuery.isPending ? (
            <div className="vs-skeleton-card" />
          ) : alarmsQuery.isError ? (
            <div className="vs-panel" role="alert">
              <p>告警记录加载失败。</p>
              <button
                className="vs-chip vs-focus"
                onClick={() => void alarmsQuery.refetch()}
                type="button"
              >
                重试
              </button>
            </div>
          ) : (alarmsQuery.data ?? []).length === 0 ? (
            <p className="vs-empty">当前筛选没有告警记录。清除筛选后再看。</p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>严重度</TableHead>
                    <TableHead>分类</TableHead>
                    <TableHead>原因</TableHead>
                    <TableHead>步骤</TableHead>
                    <TableHead>首次</TableHead>
                    <TableHead>最近</TableHead>
                    <TableHead>次数</TableHead>
                    <TableHead>状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(alarmsQuery.data ?? []).map((alarm) => (
                    <TableRow data-testid="alarm-row" key={alarm.id}>
                      <TableCell>
                        <StatusChip
                          color={
                            ALARM_SEVERITY_COLOR[alarm.severity] ??
                            "var(--vs-off)"
                          }
                        >
                          {ALARM_SEVERITY_LABEL[alarm.severity] ??
                            alarm.severity}
                        </StatusChip>
                      </TableCell>
                      <TableCell>
                        {ALARM_CATEGORY_LABEL[alarm.category] ?? alarm.category}
                      </TableCell>
                      <TableCell>
                        {alarm.reason_code
                          ? `${alarm.reason_code} · ${REASON_CODE_LABEL[alarm.reason_code] ?? ""}`
                          : "—"}
                      </TableCell>
                      <TableCell>{alarm.step_key ?? "—"}</TableCell>
                      <TableCell>
                        {formatDateTime(alarm.first_seen_at)}
                      </TableCell>
                      <TableCell>{formatTime(alarm.last_seen_at)}</TableCell>
                      <TableCell>{alarm.occurrence_count}</TableCell>
                      <TableCell>
                        {ALARM_STATUS_LABEL[alarm.status] ?? alarm.status}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="vs-empty">
                告警确认/解决接口已可用，本切片未开放操作入口。
              </p>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
