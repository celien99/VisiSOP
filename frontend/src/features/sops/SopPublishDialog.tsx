import { useMutation, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { toast } from "sonner"
import type { SopVersionRead } from "@/client"
import { SopsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { queryKeys } from "@/lib/queryKeys"

type SopPublishDialogProps = {
  sopId: string
  version: SopVersionRead
  onClose: () => void
  onPublished: (versionId: string) => void
}

export function SopPublishDialog({
  sopId,
  version,
  onClose,
  onPublished,
}: SopPublishDialogProps) {
  const queryClient = useQueryClient()

  const publish = useMutation({
    mutationFn: async () => SopsService.publishSop({ path: { sop_id: sopId } }),
    onError: (error) => {
      if (isAxiosError(error) && error.response?.status === 409) {
        toast.error("该版本已发布，不能再发布一次")
        void queryClient.invalidateQueries({ queryKey: queryKeys.sop(sopId) })
        return
      }
      toast.error("发布失败，请先通过校验")
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sops }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sop(sopId) }),
      ])
      toast.success(`v${version.version} 发布成功`)
      onPublished(version.id)
      onClose()
    },
  })

  return (
    <Dialog onOpenChange={(open) => !open && onClose()} open>
      <DialogContent className="vs-dialog border-line bg-surface text-ink shadow-none">
        <DialogHeader>
          <DialogTitle className="vs-panel__title">
            发布 v{version.version}
          </DialogTitle>
        </DialogHeader>
        <p className="vs-panel__hint">
          发布后该版本不可修改，执行将固定引用这个版本。需要修改时创建新版本。
        </p>
        <div className="vs-dialog__actions">
          <button className="vs-chip vs-focus" onClick={onClose} type="button">
            取消
          </button>
          <button
            className="vs-action vs-focus"
            disabled={publish.isPending}
            onClick={() => publish.mutate()}
            type="button"
          >
            {publish.isPending ? "发布中…" : "确认发布"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
