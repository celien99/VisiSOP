import { useMutation } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"
import type { SopValidationRead, SopVersionRead } from "@/client"
import { SopsService } from "@/client"
import { Label } from "@/components/ui/label"
import { SopPublishDialog } from "./SopPublishDialog"

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

type SopDraftEditorProps = {
  sopId: string
  version: SopVersionRead
  onPublished: (version: SopVersionRead) => void
}

export function SopDraftEditor({
  sopId,
  version,
  onPublished,
}: SopDraftEditorProps) {
  const [text, setText] = useState(() => JSON.stringify(version.dsl, null, 2))
  const [report, setReport] = useState<SopValidationRead | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)

  const verify = useMutation({
    mutationFn: async (dsl: Record<string, unknown>) => {
      // Validate what the operator sees: save the draft, then ask the server.
      await SopsService.updateSopDraft({
        body: { dsl },
        path: { sop_id: sopId },
      })
      const response = await SopsService.validateSop({
        path: { sop_id: sopId },
      })
      return response.data
    },
    onError: () => {
      setReport(null)
      toast.error("校验请求失败，请稍后重试")
    },
    onSuccess: (result) => setReport(result),
  })

  const handleValidate = () => {
    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch {
      setLocalError("DSL 不是合法 JSON")
      setReport(null)
      return
    }
    if (!isRecord(parsed)) {
      setLocalError("DSL 必须是 JSON 对象")
      setReport(null)
      return
    }
    setLocalError(null)
    verify.mutate(parsed)
  }

  return (
    <div className="vs-panel">
      <h2 className="vs-panel__title">草稿 v{version.version}</h2>
      <p className="vs-panel__hint">
        编辑后先验证；验证通过才能发布。前端不做语义校验，问题由后端给出。
      </p>

      <div className="vs-field">
        <Label htmlFor="sop-dsl">DSL JSON</Label>
        <textarea
          className="vs-textarea"
          id="sop-dsl"
          onChange={(event) => {
            setText(event.target.value)
            setReport(null)
            setLocalError(null)
          }}
          spellCheck={false}
          value={text}
        />
      </div>

      {localError ? (
        <p className="vs-issue" role="alert">
          {localError}
        </p>
      ) : null}

      {report ? (
        report.valid ? (
          <p className="vs-ok-text">校验通过</p>
        ) : (
          <ul className="vs-issues">
            {report.issues.map((issue) => (
              <li
                className="vs-issue"
                key={`${issue.code}-${issue.step_key ?? ""}`}
              >
                <strong>{issue.code}</strong> {issue.message}
                {issue.step_key ? ` · 步骤 ${issue.step_key}` : ""}
              </li>
            ))}
          </ul>
        )
      ) : null}

      <div className="vs-dialog__actions">
        <button
          className="vs-chip vs-focus"
          disabled={verify.isPending}
          onClick={handleValidate}
          type="button"
        >
          {verify.isPending ? "校验中…" : "验证"}
        </button>
        <button
          className="vs-action vs-focus"
          disabled={!report?.valid}
          onClick={() => setPublishing(true)}
          type="button"
        >
          发布
        </button>
      </div>

      {publishing ? (
        <SopPublishDialog
          onClose={() => setPublishing(false)}
          onPublished={onPublished}
          sopId={sopId}
          version={version}
        />
      ) : null}
    </div>
  )
}
