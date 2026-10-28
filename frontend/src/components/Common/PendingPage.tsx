import { Link } from "@tanstack/react-router"

type PendingPageProps = {
  code: string
  title: string
  summary: string
  dependencies: string[]
  showBack?: boolean
}

export function PendingPage({
  code,
  title,
  summary,
  dependencies,
  showBack = true,
}: PendingPageProps) {
  return (
    <div className="vs-page">
      <p className="vs-page__code">{code}</p>
      <h1 className="vs-page__title">{title}</h1>
      <p className="vs-page__lede">{summary}</p>

      <section className="vs-facts">
        <h2 className="vs-page__code">依赖 / DEPENDENCIES</h2>
        <ul>
          {dependencies.map((dependency) => (
            <li className="vs-facts__item" key={dependency}>
              {dependency}
            </li>
          ))}
        </ul>
      </section>

      <p className="vs-page__lede">
        Phase 1 不提供演示数据。接口与权限到位后，此页按设计规范接入。
      </p>
      {showBack ? (
        <Link className="vs-action vs-focus" to="/">
          返回监控墙
        </Link>
      ) : null}
    </div>
  )
}
