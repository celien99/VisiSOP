import type { EvidenceRead } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { apiUrl } from "@/lib/api"

const STATUS_LABEL: Record<string, string> = {
  AVAILABLE: "可用",
  PENDING_VERIFY: "待校验",
  MISSING: "缺失",
}

export function EvidenceViewer({
  evidence,
  onClose,
}: {
  evidence: EvidenceRead | null
  onClose: () => void
}) {
  return (
    <Dialog
      onOpenChange={(open) => !open && onClose()}
      open={evidence !== null}
    >
      <DialogContent className="vs-dialog max-w-3xl border-line bg-surface text-ink shadow-none">
        <DialogHeader>
          <DialogTitle className="vs-panel__title">
            证据{" "}
            {evidence?.status
              ? (STATUS_LABEL[evidence.status] ?? "不可用")
              : ""}
          </DialogTitle>
        </DialogHeader>
        {evidence ? (
          <div className="vs-evidence-viewer">
            <img
              alt={`证据 ${evidence.event_id} 画面`}
              className="vs-evidence-viewer__image"
              src={apiUrl(evidence.url)}
            />
            <dl className="vs-evidence-viewer__meta">
              <dt>证据 ID</dt>
              <dd>{evidence.id}</dd>
              <dt>事件 ID</dt>
              <dd>{evidence.event_id}</dd>
              <dt>SHA-256</dt>
              <dd>{evidence.sha256 ?? "—"}</dd>
              <dt>尺寸</dt>
              <dd>
                {evidence.width && evidence.height
                  ? `${evidence.width}×${evidence.height}`
                  : "不可用"}
              </dd>
            </dl>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
