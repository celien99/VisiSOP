import { createFileRoute } from "@tanstack/react-router"
import { SopsPage } from "@/features/sops/SopsPage"

export const Route = createFileRoute("/_layout/sops")({
  component: SopsPage,
  head: () => ({ meta: [{ title: "SOP 标准 — VisiSOP" }] }),
})
