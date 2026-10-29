import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/stations/$stationId")({
  component: StationRoute,
  head: () => ({ meta: [{ title: "工位详情 — VisiSOP" }] }),
})

// Placeholder until the station detail page lands; the wall's typed Link
// needs the route to exist.
function StationRoute() {
  const { stationId } = Route.useParams()
  return (
    <PendingPage
      code={`STATION / ${stationId}`}
      dependencies={[
        "工位运行时快照与执行详情接口",
        "相机健康与预览字段",
        "证据可用性字段",
      ]}
      summary="工位详情尚未接入。接口到位后，这里显示当前执行的步骤轨、活动步骤的证据与系统健康；预览失败不影响过程事实。"
      title="工位详情"
    />
  )
}
