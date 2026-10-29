import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { useState } from "react"
import { toast } from "sonner"
import type { EvidenceRead, StepRead } from "@/client"
import { ExecutionsService, StationsService } from "@/client"
import { StatusChip } from "@/components/Common/StatusChip"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { formatDateTime, formatTime } from "@/lib/format"
import { queryKeys } from "@/lib/queryKeys"
import {
  EXECUTION_STATUS_COLOR,
  EXECUTION_STATUS_LABEL,
  STEP_STATUS_LABEL,
} from "@/lib/status"
import { EvidenceViewer } from "./EvidenceViewer"
import { ExecutionFacts } from "./ExecutionFacts"
import { StepReviewDialog } from "./StepReviewDialog"
import { Timeline } from "./Timeline"

type ExecutionAction = "pause" | "resume" | "abort"

export function ExecutionDetailPage({ executionId }: { executionId: string }) {
  const queryClient = useQueryClient()
  const [reviewStep, setReviewStep] = useState<StepRead | null>(null)
  const [evidence, setEvidence] = useState<EvidenceRead | null>(null)
  const [abortOpen, setAbortOpen] = useState(false)
  const [abortReason, setAbortReason] = useState("")

  const executionQuery = useQuery({
    queryKey: queryKeys.execution(executionId),
    queryFn: async () => {
      const response = await ExecutionsService.getExecution({
        path: { execution_id: executionId },
      })
      return response.data
    },
    refetchInterval: 5000,
  })
  const execution = executionQuery.data

  const timelineQuery = useQuery({
    enabled: Boolean(execution),
    queryKey: queryKeys.executionTimeline(executionId),
    queryFn: async () => {
      const response = await ExecutionsService.getExecutionTimeline({
        path: { execution_id: executionId },
      })
      return response.data
    },
    refetchInterval: 5000,
  })

  const systemQuery = useQuery({
    enabled: Boolean(execution),
    queryKey: queryKeys.stationRuntimeState(execution?.station_id ?? ""),
    queryFn: async () => {
      const response = await StationsService.getStationRuntimeState({
        path: { station_id: execution?.station_id ?? "" },
      })
      return response.data
    },
    refetchInterval: 5000,
  })

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.execution(executionId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.executionTimeline(executionId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.stationRuntimeStates,
      }),
    ])

  const action = useMutation({
    mutationFn: async (input: { action: ExecutionAction; reason?: string }) => {
      const path = { execution_id: executionId }
      if (input.action === "pause")
        return ExecutionsService.pauseExecution({ path })
      if (input.action === "resume")
        return ExecutionsService.resumeExecution({ path })
      return ExecutionsService.abortExecution({
        body: { reason: input.reason ?? "" },
        path,
      })
    },
    onError: (error) => {
      if (isAxiosError(error) && error.response?.status === 409) {
        toast.error("状态已变化，请刷新后重试")
        void refresh()
        return
      }
      toast.error("操作失败，请稍后重试")
    },
    onSuccess: async (_data, input) => {
      setAbortOpen(false)
      setAbortReason("")
      await refresh()
      toast.success(input.action === "abort" ? "执行已中止" : "状态已更新")
    },
  })

  if (executionQuery.isPending) {
    return (
      <div className="vs-page">
        <div className="vs-skeleton-card" />
      </div>
    )
  }

  if (executionQuery.isError || !execution) {
    return (
      <div className="vs-page">
        <p className="vs-page__code">EXECUTION / {executionId}</p>
        <h1 className="vs-page__title">执行详情</h1>
        <div className="vs-panel" role="alert">
          <p>执行详情加载失败。已显示的内容不会被改写。</p>
          <button
            className="vs-chip vs-focus"
            onClick={() => void executionQuery.refetch()}
            type="button"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  const can = (name: string) => execution.allowed_actions.includes(name)
  const reviewSteps = execution.steps.filter((step) =>
    step.allowed_actions.includes("REVIEW"),
  )

  return (
    <div className="vs-page">
      <p className="vs-page__code">EXECUTION / {execution.id}</p>
      <h1 className="vs-page__title">执行详情</h1>

      <header className="vs-detail-head">
        <Link
          className="vs-action vs-focus"
          params={{ stationId: execution.station_id }}
          to="/stations/$stationId"
        >
          工位 {execution.station_id}
        </Link>
        <span className="vs-detail-head__fact">
          SOP-{execution.sop_key} v{execution.sop_version}
        </span>
        <span className="vs-detail-head__fact">
          sha256:{execution.sop_content_hash.slice(0, 8)}…
        </span>
        <StatusChip
          color={EXECUTION_STATUS_COLOR[execution.status] ?? "var(--vs-off)"}
        >
          {EXECUTION_STATUS_LABEL[execution.status] ?? execution.status}
        </StatusChip>
        <span className="vs-detail-head__fact">
          {formatDateTime(execution.started_at)}
          {execution.finished_at
            ? ` → ${formatDateTime(execution.finished_at)}`
            : ""}
        </span>
        <span className="vs-detail-head__fact">
          快照 {formatTime(execution.server_time)}
        </span>

        <div className="vs-detail-head__actions">
          {can("PAUSE") ? (
            <button
              className="vs-chip vs-focus"
              onClick={() => action.mutate({ action: "pause" })}
              type="button"
            >
              暂停
            </button>
          ) : null}
          {can("RESUME") ? (
            <button
              className="vs-chip vs-focus"
              onClick={() => action.mutate({ action: "resume" })}
              type="button"
            >
              继续
            </button>
          ) : null}
          {can("ABORT") ? (
            <button
              className="vs-chip vs-focus"
              onClick={() => setAbortOpen(true)}
              type="button"
            >
              中止
            </button>
          ) : null}
        </div>
      </header>

      {reviewSteps.length > 0 ? (
        <section className="vs-panel vs-review-bar">
          <h2 className="vs-panel__title">待复核步骤</h2>
          <ul className="vs-rows">
            {reviewSteps.map((step) => (
              <li className="vs-row" key={step.key}>
                <span className="vs-row__main">
                  {step.name} · {STEP_STATUS_LABEL[step.status] ?? step.status}
                </span>
                <button
                  className="vs-chip vs-focus"
                  onClick={() => setReviewStep(step)}
                  type="button"
                >
                  复核
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <ExecutionFacts
        execution={execution}
        onOpenEvidence={setEvidence}
        system={systemQuery.data ?? null}
      />

      <section className="vs-panel vs-timeline-panel">
        <h2 className="vs-panel__title">时间线</h2>
        {timelineQuery.isError ? (
          <div role="alert">
            <p>时间线加载失败。</p>
            <button
              className="vs-chip vs-focus"
              onClick={() => void timelineQuery.refetch()}
              type="button"
            >
              重试
            </button>
          </div>
        ) : (
          <Timeline items={timelineQuery.data ?? []} />
        )}
      </section>

      <EvidenceViewer evidence={evidence} onClose={() => setEvidence(null)} />

      {reviewStep ? (
        <StepReviewDialog
          executionId={executionId}
          onClose={() => setReviewStep(null)}
          step={reviewStep}
        />
      ) : null}

      {abortOpen ? (
        <Dialog onOpenChange={(open) => !open && setAbortOpen(false)} open>
          <DialogContent className="vs-dialog border-line bg-surface text-ink shadow-none">
            <DialogHeader>
              <DialogTitle className="vs-panel__title">中止执行</DialogTitle>
            </DialogHeader>
            <p className="vs-panel__hint">
              中止后不会继续接受事件，当前步骤不会自动完成。请填写理由。
            </p>
            <label className="vs-field__label" htmlFor="abort-reason">
              理由
            </label>
            <input
              className="vs-input"
              id="abort-reason"
              onChange={(event) => setAbortReason(event.target.value)}
              value={abortReason}
            />
            <div className="vs-dialog__actions">
              <button
                className="vs-chip vs-focus"
                onClick={() => setAbortOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="vs-chip vs-focus"
                disabled={!abortReason.trim() || action.isPending}
                onClick={() =>
                  action.mutate({ action: "abort", reason: abortReason.trim() })
                }
                type="button"
              >
                确认中止
              </button>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  )
}
