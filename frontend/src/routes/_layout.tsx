import { createFileRoute, Link, Outlet } from "@tanstack/react-router"

import { Appearance } from "@/components/Common/Appearance"
import { Footer } from "@/components/Common/Footer"

export const Route = createFileRoute("/_layout")({
  component: Layout,
})

function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b bg-background px-6">
        <Link to="/" className="text-lg font-bold">
          VisiSOP
        </Link>
        <Appearance />
      </header>
      <main className="flex-1 p-6 md:p-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
      <Footer />
    </div>
  )
}
