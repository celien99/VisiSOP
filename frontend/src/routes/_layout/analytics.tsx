import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/analytics")({
  component: AnalyticsRoute,
  head: () => ({ meta: [{ title: "看板 · VisiSOP" }] }),
})

function AnalyticsRoute() {
  return (
    <PendingPage
      code="ANALYTICS / 看板"
      dependencies={[
        "按时间与区域聚合的作业计数接口",
        "原因码分布与复核时长接口",
        "机位可用率与中断时段接口",
        "记录列表接口，供图表下钻",
      ]}
      summary="分析看板尚未接入。接口到位后，这里按时间范围给出作业量、异常、待确认与平均确认时长，再用单轴单色相的趋势、机位可用率和原因分布回答“这段时间发生了什么”；前端只按后端返回的原因码归类，不做归因。"
      title="分析看板"
    />
  )
}
