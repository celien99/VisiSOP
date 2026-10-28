import { Link } from "@tanstack/react-router"

const ErrorComponent = () => {
  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center bg-casing px-6 text-ink"
      data-testid="error-component"
    >
      <p className="vs-page__code">ERROR / 加载失败</p>
      <h1 className="vs-page__title mt-2">页面未能加载</h1>
      <p className="vs-page__lede text-center">
        请检查快照接口与网络连接。已加载的数据不会被改写。
      </p>
      <Link className="vs-action vs-focus" to="/">
        返回监控墙
      </Link>
    </div>
  )
}

export default ErrorComponent
