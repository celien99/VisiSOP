import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/sops")({
  component: SopsRoute,
  head: () => ({ meta: [{ title: "标准 · VisiSOP" }] }),
})

function SopsRoute() {
  return (
    <PendingPage
      code="STANDARD / 标准"
      dependencies={[
        "SOP 列表与版本接口",
        "校验与发布动作接口",
        "只读 DAG 所需的节点与迁移数据",
      ]}
      summary="SOP 版本列表、校验与只读 DAG 尚未接入。SOP 是版本化 DSL，已发布版本不可变，执行固定 sop_version_id；前端不推导结论，也不提供图形编辑器。"
      title="标准（SOP 版本）"
    />
  )
}
