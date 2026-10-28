import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/stations")({
  component: StationsRoute,
  head: () => ({ meta: [{ title: "工位 · VisiSOP" }] }),
})

function StationsRoute() {
  return (
    <PendingPage
      code="STATIONS / 工位"
      dependencies={[
        "工位列表与当前执行快照接口",
        "设备与相机健康接口",
        "证据元数据接口；预览流不作为证据",
      ]}
      summary="工位列表与单工位详情尚未接入。接口到位后，这里列出每个机位的当前执行、当前步骤、系统健康与待确认数量；过程事实与系统事实分开显示，预览失败不影响健康显示。"
      title="工位总览"
    />
  )
}
