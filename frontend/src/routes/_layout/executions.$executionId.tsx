import { createFileRoute } from "@tanstack/react-router"
import { ExecutionDetailPage } from "@/features/execution/ExecutionDetailPage"

export const Route = createFileRoute("/_layout/executions/$executionId")({
  component: ExecutionRoute,
  head: () => ({ meta: [{ title: "执行详情 — VisiSOP" }] }),
})

function ExecutionRoute() {
  const { executionId } = Route.useParams()
  return <ExecutionDetailPage executionId={executionId} />
}
