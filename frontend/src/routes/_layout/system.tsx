import { createFileRoute } from "@tanstack/react-router"
import { SystemPage } from "@/features/system/SystemPage"

export const Route = createFileRoute("/_layout/system")({
  component: SystemPage,
  head: () => ({ meta: [{ title: "系统健康 — VisiSOP" }] }),
})
