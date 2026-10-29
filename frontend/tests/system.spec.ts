import { expect, test } from "@playwright/test"

const T = "2026-01-01T12:00:00Z"

test("system health never masquerades as process compliance", async ({
  page,
}) => {
  await page.route("**/api/health/summary", (route) =>
    route.fulfill({
      json: {
        database: "UNAVAILABLE",
        server_time: "2026-01-01T12:00:20Z",
        runtimes: [
          {
            runtime_id: "runtime-01",
            base_url: "http://127.0.0.1:8001",
            preview_base_url: "http://127.0.0.1:8001",
            version: "0.1.0",
            camera_ids: ["cam-01"],
            status: "UNAVAILABLE",
            last_heartbeat_at: T,
          },
        ],
        cameras: [
          {
            id: "cam-01",
            code: "CAM-01",
            name: "主相机",
            runtime_id: "runtime-01",
            source_type: "gige",
            preview_url: "http://127.0.0.1:8001/stream/cam-01",
            snapshot_url: "http://127.0.0.1:8001/snapshot/cam-01",
            health: "DEGRADED",
            last_frame_at: T,
            created_at: T,
          },
        ],
      },
    }),
  )

  await page.goto("/system")
  await expect(page.getByTestId("system-health")).toContainText("数据库")
  await expect(page.getByTestId("system-health")).toContainText("不可用")
  await expect(page.getByTestId("system-health")).not.toContainText("已完成")
})
