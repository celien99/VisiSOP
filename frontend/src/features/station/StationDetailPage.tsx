import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { useState } from "react"
import { toast } from "sonner"
import { ExecutionsService, SopsService, StationsService } from "@/client"
import { StatusChip } from "@/components/Common/StatusChip"
import { ExecutionFacts } from "@/features/execution/ExecutionFacts"
import { StepRail } from "@/features/execution/StepRail"
import { PreviewPanel } from "@/features/wall/PreviewPanel"
import { isStale } from "@/lib/format"
import { queryKeys } from "@/lib/queryKeys"
import {
  EXECUTION_STATUS_COLOR,
  EXECUTION_STATUS_LABEL,
  HEALTH_LABEL,
} from "@/lib/status"

const BUSY = ["RUNNING", "REVIEW", "ALARM"]

export function StationDetailPage({ stationId }: { stationId: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const stateQuery = useQuery({
    queryKey: queryKeys.stationRuntimeState(stationId),
    queryFn: async () => {
      const response = await StationsService.getStationRuntimeState({
        path: { station_id: stationId },
      })
      return response.data
    },
    refetchInterval: 5000,
  })
  const state = stateQuery.data

  const executionQuery = useQuery({
    enabled: Boolean(state?.execution),
    queryKey: queryKeys.execution(state?.execution?.id ?? ""),
    queryFn: async () => {
      const response = await ExecutionsService.getExecution({
        path: { execution_id: state?.execution?.id ?? "" },
      })
      return response.data
    },
    refetchInterval: 5000,
  })

  const sopsQuery = useQuery({
    queryKey: queryKeys.sops,
    queryFn: async () => {
      const response = await SopsService.listSops()
      return response.data
    },
  })

  // Only published versions can start an execution; the backend rejects the rest.
  const published = (sopsQuery.data ?? []).flatMap((sop) =>
    sop.versions
      .filter((version) => version.id === sop.latest_published_version_id)
      .map((version) => ({ sop, version })),
  )
  const [choice, setChoice] = useState("")
  const selected = choice || published[0]?.version.id || ""

  const start = useMutation({
    mutationFn: async () =>
      ExecutionsService.createExecution({
        body: { sop_version_id: selected },
        path: { station_id: stationId },
      }),
    onError: (error) => {
      if (isAxiosError(error) && error.response?.status === 409) {
        toast.error("已有进行中的执行，请先完成复核")
        return
      }
      toast.error("开始执行失败，请检查工位与 SOP 版本")
    },
    onSuccess: async (response) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.stationRuntimeStates,
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.stationRuntimeState(stationId),
        }),
        queryClient.invalidateQueries({ queryKey: ["executions"] }),
      ])
      await navigate({
        params: { executionId: response.data.id },
        to: "/executions/$executionId",
      })
    },
  })

  if (!state && stateQuery.isPending) {
    return (
      <div className="vs-page">
        <div className="vs-skeleton-card" />
      </div>
    )
  }

  if (!state) {
    return (
      <div className="vs-page">
        <p className="vs-page__code">STATION / {stationId}</p>
        <h1 className="vs-page__title">工位详情</h1>
        <div className="vs-panel" role="alert">
          <p>工位快照加载失败。已显示的内容不会被改写。</p>
          <button
            className="vs-chip vs-focus"
            onClick={() => void stateQuery.refetch()}
            type="button"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  const { station, camera, execution } = state
  const busy = BUSY.includes(state.process_status) || !selected
  const disabledReason = selected
    ? "当前执行尚未结束，先完成复核或等待结束"
    : "没有已发布的 SOP 版本，先在标准页发布"

  return (
    <div className="vs-page">
      <p className="vs-page__code">STATION / {station.code}</p>
      <h1 className="vs-page__title">{station.name}</h1>

      {stateQuery.isError ? (
        <div className="vs-wall__error" role="alert">
          <p>刷新失败，显示上次快照。</p>
          <button
            className="vs-chip vs-focus"
            onClick={() => void stateQuery.refetch()}
            type="button"
          >
            重试
          </button>
        </div>
      ) : null}

      <header className="vs-detail-head">
        <span className="vs-detail-head__fact">区域 {station.zone ?? "—"}</span>
        <span className="vs-detail-head__fact">
          相机{" "}
          {camera
            ? `${camera.code} · ${HEALTH_LABEL[camera.health] ?? camera.health}`
            : "未绑定"}
        </span>
        {execution ? (
          <StatusChip
            color={EXECUTION_STATUS_COLOR[execution.status] ?? "var(--vs-off)"}
          >
            {EXECUTION_STATUS_LABEL[execution.status] ?? execution.status}
          </StatusChip>
        ) : null}
        {execution ? (
          <button
            className="vs-chip vs-focus"
            onClick={() =>
              void navigate({
                params: { executionId: execution.id },
                to: "/executions/$executionId",
              })
            }
            type="button"
          >
            打开执行详情
          </button>
        ) : null}
        <div className="vs-detail-head__actions">
          {sopsQuery.isError ? (
            <span className="vs-row__meta">
              SOP 列表加载失败，暂时无法开始执行
            </span>
          ) : null}
          {published.length > 0 ? (
            <select
              aria-label="发布版本"
              className="vs-select"
              onChange={(event) => setChoice(event.target.value)}
              value={selected}
            >
              {published.map(({ sop, version }) => (
                <option key={version.id} value={version.id}>
                  v{version.version} · {sop.name}
                </option>
              ))}
            </select>
          ) : null}
          <button
            className="vs-chip vs-focus"
            disabled={busy || start.isPending}
            onClick={() => start.mutate()}
            title={busy ? disabledReason : undefined}
            type="button"
          >
            {start.isPending ? "正在开始…" : "开始执行"}
          </button>
        </div>
      </header>

      <div className="vs-station-grid">
        <PreviewPanel
          alt={`${station.code} ${station.name} 画面`}
          health={camera?.health ?? "UNAVAILABLE"}
          key={`${state.preview_url ?? ""}|${camera?.health ?? ""}`}
          lastFrameAt={state.last_frame_at}
          previewUrl={state.preview_url}
          snapshotUrl={state.snapshot_url}
          stale={isStale(state.last_frame_at, state.server_time)}
        />
        <div className="vs-panel">
          <h2 className="vs-panel__title">当前执行</h2>
          <p className="vs-panel__hint">
            {execution
              ? `SOP-${execution.sop_key} v${execution.sop_version} · ${execution.current_step_name ?? "—"}`
              : "暂无执行"}
          </p>
          <StepRail steps={state.steps} />
        </div>
      </div>

      {execution && executionQuery.isPending ? (
        <div className="vs-skeleton-card" />
      ) : execution && executionQuery.isError ? (
        <div className="vs-panel" role="alert">
          <p>执行详情加载失败，工位快照仍然有效。</p>
          <button
            className="vs-chip vs-focus"
            onClick={() => void executionQuery.refetch()}
            type="button"
          >
            重试
          </button>
        </div>
      ) : (
        <ExecutionFacts
          execution={executionQuery.data ?? null}
          system={state}
        />
      )}
    </div>
  )
}
