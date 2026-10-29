import { createFileRoute } from "@tanstack/react-router"
import { StationDetailPage } from "@/features/station/StationDetailPage"

export const Route = createFileRoute("/_layout/stations/$stationId")({
  component: StationRoute,
  head: () => ({ meta: [{ title: "工位详情 — VisiSOP" }] }),
})

function StationRoute() {
  const { stationId } = Route.useParams()
  return <StationDetailPage stationId={stationId} />
}
