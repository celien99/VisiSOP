import { useMutation, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useState } from "react"
import { toast } from "sonner"
import type { ReviewDecision, StepRead } from "@/client"
import { ExecutionsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { queryKeys } from "@/lib/queryKeys"

type StepReviewDialogProps = {
  executionId: string
  step: StepRead
  onClose: () => void
}

const DECISIONS: { value: ReviewDecision; label: string }[] = [
  { value: "MARK_COMPLETED", label: "标记完成" },
  { value: "MARK_FAILED", label: "标记失败" },
]

export function StepReviewDialog({
  executionId,
  step,
  onClose,
}: StepReviewDialogProps) {
  const queryClient = useQueryClient()
  const [operator, setOperator] = useState("")
  const [reason, setReason] = useState("")
  const [comment, setComment] = useState("")
  const [decision, setDecision] = useState<ReviewDecision | null>(null)
  const [evidenceIds, setEvidenceIds] = useState<string[]>([])
  const availableEvidence = step.evidence.filter(
    (asset) => asset.status === "AVAILABLE",
  )

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.execution(executionId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.executionTimeline(executionId),
      }),
    ])

  const review = useMutation({
    mutationFn: async () => {
      const choice = decision
      if (!choice) throw new Error("decision required")
      return ExecutionsService.reviewStep({
        body: {
          comment: comment.trim() || null,
          decision: choice,
          evidence_ids: evidenceIds,
          operator: operator.trim(),
          reason: reason.trim(),
        },
        path: { execution_id: executionId, step_key: step.key },
      })
    },
    onError: (error) => {
      if (isAxiosError(error) && error.response?.status === 409) {
        toast.error("状态已变化，请刷新后重新确认")
        void refresh()
        return
      }
      toast.error("复核提交失败，请检查输入后重试")
    },
    onSuccess: async () => {
      await refresh()
      toast.success(`已提交复核 · 步骤 ${step.name}`)
      onClose()
    },
  })

  return (
    <Dialog onOpenChange={(open) => !open && onClose()} open>
      <DialogContent className="vs-dialog border-line bg-surface text-ink shadow-none">
        <DialogHeader>
          <DialogTitle className="vs-panel__title">
            复核 · {step.name}
          </DialogTitle>
        </DialogHeader>
        <p className="vs-panel__hint">
          决定、理由必填；提交后不可修改，审计只追加。
        </p>

        <fieldset className="vs-field">
          <legend className="vs-field__label">决定</legend>
          <div className="vs-field__row">
            {DECISIONS.map((option) => (
              <label className="vs-radio" key={option.value}>
                <input
                  checked={decision === option.value}
                  name="review-decision"
                  onChange={() => setDecision(option.value)}
                  type="radio"
                  value={option.value}
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="vs-field">
          <Label htmlFor="review-operator">操作者</Label>
          <input
            className="vs-input"
            id="review-operator"
            onChange={(event) => setOperator(event.target.value)}
            value={operator}
          />
        </div>

        <div className="vs-field">
          <Label htmlFor="review-reason">理由</Label>
          <input
            className="vs-input"
            id="review-reason"
            onChange={(event) => setReason(event.target.value)}
            value={reason}
          />
        </div>

        <div className="vs-field">
          <Label htmlFor="review-comment">备注</Label>
          <input
            className="vs-input"
            id="review-comment"
            onChange={(event) => setComment(event.target.value)}
            value={comment}
          />
        </div>

        {availableEvidence.length > 0 ? (
          <fieldset className="vs-field">
            <legend className="vs-field__label">引用证据</legend>
            {availableEvidence.map((asset) => (
              <label className="vs-radio" key={asset.id}>
                <input
                  checked={evidenceIds.includes(asset.id)}
                  onChange={() =>
                    setEvidenceIds((current) =>
                      current.includes(asset.id)
                        ? current.filter((id) => id !== asset.id)
                        : [...current, asset.id],
                    )
                  }
                  type="checkbox"
                />
                {asset.event_id}
              </label>
            ))}
          </fieldset>
        ) : null}

        <div className="vs-dialog__actions">
          <button className="vs-chip vs-focus" onClick={onClose} type="button">
            取消
          </button>
          <button
            className="vs-action vs-focus"
            disabled={
              !decision ||
              !operator.trim() ||
              !reason.trim() ||
              review.isPending
            }
            onClick={() => review.mutate()}
            type="button"
          >
            {review.isPending ? "提交中…" : "提交复核"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
