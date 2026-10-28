import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/")({
  component: WallRoute,
  head: () => ({ meta: [{ title: "监控墙 · VisiSOP" }] }),
})

function WallRoute() {
  return (
    <PendingPage
      code="WALL / 监控墙"
      dependencies={[
        "机位列表与当前执行快照接口",
        "步骤状态、原因码与允许动作字段",
        "画面状态字段；预览流在阶段 2 才接入",
        "设备与推理健康接口，与工艺事实分开",
      ]}
      summary="多机位监控墙尚未接入。接口到位后，每格显示画面、机位、状态章、SOP 步骤轨与当前步骤；需要人处理的机位带处置条与等待时长，没有信号的机位明确显示离线，不用最后一帧冒充。"
      showBack={false}
      title="多机位监控墙"
    />
  )
}
