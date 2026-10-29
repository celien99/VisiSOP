import { createFileRoute, useNavigate } from "@tanstack/react-router"
import type { WallSearch } from "@/features/wall/WallPage"
import { WallPage } from "@/features/wall/WallPage"

export const Route = createFileRoute("/_layout/")({
  component: WallRoute,
  head: () => ({ meta: [{ title: "多机位监控墙 — VisiSOP" }] }),
  validateSearch: (search: Record<string, unknown>): WallSearch => ({
    zone:
      typeof search.zone === "string" && search.zone ? search.zone : undefined,
    // The router's default parser JSON-decodes "1" into a number.
    attention:
      search.attention === "1" || search.attention === 1 ? "1" : undefined,
    sort: search.sort === "attention" ? "attention" : undefined,
    focus:
      typeof search.focus === "string" && search.focus
        ? search.focus
        : undefined,
  }),
})

function WallRoute() {
  const search = Route.useSearch()
  const navigate = useNavigate()
  return (
    <WallPage
      onSearchChange={(patch) =>
        navigate({ search: { ...search, ...patch }, to: "/" })
      }
      search={search}
    />
  )
}
