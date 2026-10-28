import { Link } from "@tanstack/react-router"

const NotFound = () => {
  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center bg-casing px-6 text-ink"
      data-testid="not-found"
    >
      <p className="vs-page__code">404 / NOT FOUND</p>
      <h1 className="vs-page__title mt-2">页面不存在</h1>
      <p className="vs-page__lede text-center">
        地址可能已更改，或这条记录尚未接入。
      </p>
      <Link className="vs-action vs-focus" to="/">
        返回监控墙
      </Link>
    </div>
  )
}

export default NotFound
