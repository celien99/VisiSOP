import { createFileRoute, useNavigate } from "@tanstack/react-router"
import type { RecordsSearch } from "@/features/records/RecordsPage"
import { RecordsPage } from "@/features/records/RecordsPage"

export const Route = createFileRoute("/_layout/records")({
  component: RecordsRoute,
  head: () => ({ meta: [{ title: "记录 — VisiSOP" }] }),
  validateSearch: (search: Record<string, unknown>): RecordsSearch => ({
    tab: search.tab === "alarms" ? "alarms" : undefined,
    status:
      typeof search.status === "string" && search.status
        ? search.status
        : undefined,
    station_id:
      typeof search.station_id === "string" && search.station_id
        ? search.station_id
        : undefined,
  }),
})

function RecordsRoute() {
  const search = Route.useSearch()
  const navigate = useNavigate()
  return (
    <RecordsPage
      onSearchChange={(patch) =>
        navigate({ search: { ...search, ...patch }, to: "/records" })
      }
      search={search}
    />
  )
}
