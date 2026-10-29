import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useState } from "react"
import { toast } from "sonner"
import type { SopVersionRead } from "@/client"
import { SopsService } from "@/client"
import { StatusChip } from "@/components/Common/StatusChip"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { queryKeys } from "@/lib/queryKeys"
import { SopDag } from "./SopDag"
import { SopDraftEditor } from "./SopDraftEditor"

const VERSION_STATUS_LABEL: Record<string, string> = {
  DRAFT: "草稿",
  PUBLISHED: "已发布",
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function SopsPage() {
  const queryClient = useQueryClient()
  const [selectedSopId, setSelectedSopId] = useState<string | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    null,
  )
  const [confirmedVersion, setConfirmedVersion] =
    useState<SopVersionRead | null>(null)
  const [creating, setCreating] = useState(false)
  const [newKey, setNewKey] = useState("")
  const [newName, setNewName] = useState("")
  const [newDsl, setNewDsl] = useState("")
  const [newError, setNewError] = useState<string | null>(null)

  const sopsQuery = useQuery({
    queryKey: queryKeys.sops,
    queryFn: async () => {
      const response = await SopsService.listSops()
      return response.data
    },
  })
  const sops = sopsQuery.data ?? []
  const sopId = selectedSopId ?? sops[0]?.id ?? null

  const detailQuery = useQuery({
    enabled: Boolean(sopId),
    queryKey: queryKeys.sop(sopId ?? ""),
    queryFn: async () => {
      const response = await SopsService.getSop({
        path: { sop_id: sopId ?? "" },
      })
      return response.data
    },
  })
  const detail = detailQuery.data

  const versions = [...(detail?.versions ?? [])].sort(
    (a, b) => b.version - a.version,
  )
  const version =
    versions.find((item) => item.id === selectedVersionId) ?? versions[0]
  const effectiveStatus =
    version && confirmedVersion?.id === version.id
      ? confirmedVersion.status
      : version?.status

  const create = useMutation({
    mutationFn: async (dsl: Record<string, unknown>) =>
      SopsService.createSop({
        body: { dsl, key: newKey.trim(), name: newName.trim() },
      }),
    onError: (error) => {
      if (isAxiosError(error) && error.response?.status === 409) {
        toast.error("SOP key 已存在")
        return
      }
      toast.error("新建 SOP 失败，请检查输入")
    },
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sops })
      setCreating(false)
      setNewKey("")
      setNewName("")
      setNewDsl("")
      setSelectedSopId(response.data.sop_id)
      setSelectedVersionId(response.data.id)
      toast.success(`已创建 ${response.data.id}`)
    },
  })

  const handleCreate = () => {
    let parsed: unknown
    try {
      parsed = JSON.parse(newDsl || "{}")
    } catch {
      setNewError("DSL 不是合法 JSON")
      return
    }
    if (!isRecord(parsed)) {
      setNewError("DSL 必须是 JSON 对象")
      return
    }
    setNewError(null)
    create.mutate(parsed)
  }

  return (
    <div className="vs-page">
      <p className="vs-page__code">SOPS / 标准</p>
      <h1 className="vs-page__title">SOP 标准</h1>

      {sopsQuery.isError ? (
        <div className="vs-panel" role="alert">
          <p>SOP 列表加载失败。</p>
          <button
            className="vs-chip vs-focus"
            onClick={() => void sopsQuery.refetch()}
            type="button"
          >
            重试
          </button>
        </div>
      ) : null}

      <div className="vs-sops">
        <nav aria-label="SOP 列表" className="vs-list">
          {sopsQuery.isPending ? <div className="vs-skeleton-card" /> : null}
          {!sopsQuery.isPending && sops.length === 0 ? (
            <p className="vs-empty">还没有 SOP。新建后先校验，再发布。</p>
          ) : null}
          {sops.map((sop) => (
            <button
              aria-current={sop.id === sopId ? "true" : undefined}
              className="vs-list__item vs-focus"
              key={sop.id}
              onClick={() => {
                setSelectedSopId(sop.id)
                setSelectedVersionId(null)
              }}
              type="button"
            >
              <span className="vs-row__main">{sop.name}</span>
              <span className="vs-row__meta">{sop.key}</span>
            </button>
          ))}
          <button
            className="vs-chip vs-focus"
            onClick={() => setCreating(true)}
            type="button"
          >
            新建 SOP
          </button>
        </nav>

        <section className="vs-sop-detail">
          {detailQuery.isPending && sopId ? (
            <div className="vs-skeleton-card" />
          ) : null}
          {detailQuery.isError ? (
            <div className="vs-panel" role="alert">
              <p>SOP 详情加载失败。</p>
              <button
                className="vs-chip vs-focus"
                onClick={() => void detailQuery.refetch()}
                type="button"
              >
                重试
              </button>
            </div>
          ) : null}
          {detail ? (
            <>
              <header className="vs-detail-head">
                <span className="vs-detail-head__fact">{detail.key}</span>
                <span className="vs-detail-head__fact">{detail.name}</span>
                {version ? (
                  <StatusChip
                    color={
                      effectiveStatus === "PUBLISHED"
                        ? "var(--vs-ok)"
                        : "var(--vs-warn)"
                    }
                  >
                    {VERSION_STATUS_LABEL[effectiveStatus ?? ""] ??
                      effectiveStatus}
                  </StatusChip>
                ) : null}
                <div className="vs-detail-head__actions">
                  {versions.map((item) => (
                    <button
                      aria-pressed={item.id === version?.id}
                      className="vs-chip vs-focus"
                      key={item.id}
                      onClick={() => setSelectedVersionId(item.id)}
                      type="button"
                    >
                      v{item.version}
                    </button>
                  ))}
                </div>
              </header>

              {version ? (
                effectiveStatus === "DRAFT" ? (
                  <SopDraftEditor
                    key={version.id}
                    onPublished={setConfirmedVersion}
                    sopId={detail.id}
                    version={version}
                  />
                ) : (
                  <div className="vs-panel">
                    <h2 className="vs-panel__title">v{version.version} 只读</h2>
                    <p className="vs-panel__hint">
                      该版本不可修改 · sha256:{version.content_hash.slice(0, 8)}
                      …
                    </p>
                    <SopDag version={version} />
                  </div>
                )
              ) : (
                <p className="vs-empty">这个 SOP 还没有版本。</p>
              )}
            </>
          ) : null}
        </section>
      </div>

      {creating ? (
        <Dialog onOpenChange={(open) => !open && setCreating(false)} open>
          <DialogContent className="vs-dialog border-line bg-surface text-ink shadow-none">
            <DialogHeader>
              <DialogTitle className="vs-panel__title">新建 SOP</DialogTitle>
            </DialogHeader>
            <div className="vs-field">
              <Label htmlFor="new-sop-key">Key</Label>
              <input
                className="vs-input"
                id="new-sop-key"
                onChange={(event) => setNewKey(event.target.value)}
                value={newKey}
              />
            </div>
            <div className="vs-field">
              <Label htmlFor="new-sop-name">名称</Label>
              <input
                className="vs-input"
                id="new-sop-name"
                onChange={(event) => setNewName(event.target.value)}
                value={newName}
              />
            </div>
            <div className="vs-field">
              <Label htmlFor="new-sop-dsl">DSL JSON</Label>
              <textarea
                className="vs-textarea"
                id="new-sop-dsl"
                onChange={(event) => setNewDsl(event.target.value)}
                spellCheck={false}
                value={newDsl}
              />
            </div>
            {newError ? (
              <p className="vs-issue" role="alert">
                {newError}
              </p>
            ) : null}
            <div className="vs-dialog__actions">
              <button
                className="vs-chip vs-focus"
                onClick={() => setCreating(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="vs-action vs-focus"
                disabled={!newKey.trim() || !newName.trim() || create.isPending}
                onClick={handleCreate}
                type="button"
              >
                {create.isPending ? "创建中…" : "创建"}
              </button>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  )
}
