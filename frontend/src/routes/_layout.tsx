import { createFileRoute, Link, Outlet } from "@tanstack/react-router"
import { useEffect, useState } from "react"

export const Route = createFileRoute("/_layout")({
  component: Layout,
})

const NAV = [
  { to: "/", label: "监控墙", exact: true },
  { to: "/analytics", label: "看板" },
  { to: "/records", label: "记录" },
  { to: "/sops", label: "标准" },
] as const

const clockFormat = new Intl.DateTimeFormat("zh-CN", {
  hour12: false,
  hour: "2-digit",
  minute: "2-digit",
})

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  return clockFormat.format(now)
}

function Layout() {
  const clock = useClock()

  return (
    <div className="flex min-h-dvh flex-col bg-casing text-ink">
      <a className="vs-skip" href="#main">
        跳到主要内容
      </a>
      <header className="vs-topbar">
        <div className="vs-topbar__inner">
          <Link
            aria-label="VisiSOP 监控墙"
            className="vs-wordmark vs-focus"
            to="/"
          >
            <span aria-hidden="true" className="vs-wordmark__mark" />
            VisiSOP
          </Link>
          <span aria-hidden="true" className="vs-topbar__sep" />
          <nav aria-label="主导航" className="vs-nav">
            {NAV.map((item) => (
              <Link
                activeOptions={{ exact: "exact" in item }}
                activeProps={{ "aria-current": "page" }}
                className="vs-nav__link vs-focus"
                key={item.to}
                to={item.to}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="vs-topbar__right">
            <span className="vs-conn">
              <span aria-hidden="true" className="vs-conn__dot" />
              未连接
            </span>
            <span className="vs-clock">{clock}</span>
            <Link className="vs-utility vs-focus" to="/system">
              系统
            </Link>
          </div>
        </div>
      </header>
      <main className="flex-1" id="main">
        <Outlet />
      </main>
      <footer className="vs-statusbar">
        <span>Phase 1 · 接口尚未接入，页面不展示推定结果</span>
        <span>VisiSOP</span>
      </footer>
    </div>
  )
}
