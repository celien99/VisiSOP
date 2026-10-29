import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import type { StationRuntimeStateRead } from "@/client"
import { StationsService } from "@/client"
import { queryKeys } from "@/lib/queryKeys"
import { AttentionStrip } from "./AttentionStrip"
import { WallCard } from "./WallCard"

export type WallSearch = {
  zone?: string
  attention?: "1"
  sort?: "attention"
  focus?: string
}

type WallPageProps = {
  search: WallSearch
  onSearchChange: (patch: Partial<WallSearch>) => void
}

function byAttention(a: StationRuntimeStateRead, b: StationRuntimeStateRead) {
  return (a.attention_since ?? "~").localeCompare(b.attention_since ?? "~")
}

export function WallPage({ search, onSearchChange }: WallPageProps) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: queryKeys.stationRuntimeStates,
    queryFn: async () => {
      const response = await StationsService.listStationRuntimeStates()
      return response.data
    },
    refetchInterval: 5000,
  })

  const states = data ?? []
  const zones = [
    ...new Set(
      states
        .map((state) => state.station.zone)
        .filter((zone): zone is string => Boolean(zone)),
    ),
  ]
  const visible = states
    .filter((state) => !search.zone || state.station.zone === search.zone)
    .filter(
      (state) =>
        search.attention !== "1" ||
        state.process_status === "REVIEW" ||
        state.process_status === "ALARM",
    )
    .sort((a, b) =>
      search.sort === "attention"
        ? byAttention(a, b)
        : a.station.code.localeCompare(b.station.code),
    )

  useEffect(() => {
    if (!search.focus) return
    document
      .getElementById(`tile-${search.focus}`)
      ?.scrollIntoView({ block: "center" })
  }, [search.focus])

  return (
    <div className="vs-wall-page">
      <h1 className="vs-visually-hidden">多机位监控墙</h1>

      <div className="vs-filterbar">
        <label className="vs-filterbar__label" htmlFor="wall-zone">
          区域
        </label>
        <select
          className="vs-select"
          id="wall-zone"
          onChange={(event) =>
            onSearchChange({ zone: event.target.value || undefined })
          }
          value={search.zone ?? ""}
        >
          <option value="">全部区域</option>
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>

        <button
          aria-pressed={search.attention === "1"}
          className="vs-chip vs-focus"
          onClick={() =>
            onSearchChange({
              attention: search.attention === "1" ? undefined : "1",
            })
          }
          type="button"
        >
          只看需要处理
        </button>

        <label className="vs-filterbar__label" htmlFor="wall-sort">
          排序
        </label>
        <select
          className="vs-select"
          id="wall-sort"
          onChange={(event) =>
            onSearchChange({
              sort:
                event.target.value === "attention" ? "attention" : undefined,
            })
          }
          value={search.sort ?? "station"}
        >
          <option value="station">按机位</option>
          <option value="attention">按等待时长</option>
        </select>

        <span className="vs-filterbar__count">{visible.length} 机位</span>
      </div>

      <AttentionStrip
        serverTime={states[0]?.server_time ?? null}
        states={visible}
      />

      {isPending ? (
        <div className="vs-wall">
          {[0, 1, 2].map((key) => (
            <div className="vs-skeleton-card" key={key} />
          ))}
        </div>
      ) : isError ? (
        <div className="vs-wall">
          <div className="vs-wall__empty" role="alert">
            <p>工位快照加载失败。已显示的内容不会被改写。</p>
            <button
              className="vs-chip vs-focus"
              onClick={() => void refetch()}
              type="button"
            >
              重试
            </button>
          </div>
        </div>
      ) : states.length === 0 ? (
        <div className="vs-wall">
          <div className="vs-wall__empty">
            <p>暂无已配置工位。</p>
            <p>先在系统中注册工位与相机，监控墙按后端返回的工位逐格显示。</p>
          </div>
        </div>
      ) : visible.length === 0 ? (
        <div className="vs-wall">
          <div className="vs-wall__empty">
            <p>当前筛选没有需要处理的机位。</p>
            <button
              className="vs-chip vs-focus"
              onClick={() =>
                onSearchChange({ attention: undefined, zone: undefined })
              }
              type="button"
            >
              清除筛选
            </button>
          </div>
        </div>
      ) : (
        <div className="vs-wall">
          {visible.map((state) => (
            <WallCard
              focused={search.focus === state.station.id}
              key={state.station.id}
              state={state}
            />
          ))}
        </div>
      )}
    </div>
  )
}
