import { createFileRoute } from "@tanstack/react-router"
import { PendingPage } from "@/components/Common/PendingPage"

export const Route = createFileRoute("/_layout/system")({
  component: SystemRoute,
  head: () => ({ meta: [{ title: "系统 · VisiSOP" }] }),
})

function SystemRoute() {
  return (
    <PendingPage
      code="SYSTEM / 系统"
      dependencies={[
        "设备与相机健康接口",
        "推理服务健康与模型版本接口",
        "平台健康、保留策略与构建信息",
      ]}
      summary="系统配置在 Phase 1 只读。设备、推理与平台健康接口尚未接入；设备离线与“无事件”会分开显示，不用一个绿灯概括全部状态。"
      title="系统状态"
    />
  )
}
