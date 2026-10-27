import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/")({
  component: Home,
  head: () => ({
    meta: [
      {
        title: "VisiSOP",
      },
    ],
  }),
})

function Home() {
  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight">Welcome to VisiSOP</h1>
      <p className="text-muted-foreground">Your project starts here.</p>
    </div>
  )
}
