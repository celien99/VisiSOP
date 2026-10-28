import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/records")({
  component: RecordsRoute,
  head: () => ({ meta: [{ title: "记录 · VisiSOP" }] }),
})

function RecordsRoute() {
  return (
    <PendingPage
      code="RECORDS / 记录"
      dependencies={[
        "执行与告警的检索、筛选接口",
        "证据可用性字段与详情接口",
        "确认与解决动作及权限",
      ]}
      summary="记录检索尚未接入。接口到位后，执行与告警分开展示、分别计数；工艺合规与系统健康不混成一个总数，证据不可用时明确写出原因，而不是打开一个空查看器。"
      title="记录"
    />
  )
}
