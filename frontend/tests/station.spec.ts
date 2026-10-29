import { expect, test } from "@playwright/test"

const T = "2026-01-01T12:00:00Z"

const runtimeState = (over: Record<string, unknown>) => ({
  station: {
    id: "st-01",
    code: "ST-01",
    name: "演示工位",
    zone: "A",
    created_at: T,
  },
  camera: {
    id: "cam-01",
    code: "CAM-01",
    name: "主相机",
    runtime_id: "runtime-01",
    source_type: "gige",
    preview_url: "http://127.0.0.1:8001/stream/cam-01",
    snapshot_url: "http://127.0.0.1:8001/snapshot/cam-01",
    health: "HEALTHY",
    last_frame_at: T,
    created_at: T,
  },
  execution: null,
  steps: [],
  process_status: "IDLE",
  attention_since: null,
  open_alarm_count: 0,
  highest_alarm_severity: null,
  health: "HEALTHY",
  preview_url: "http://127.0.0.1:8001/stream/cam-01",
  snapshot_url: "http://127.0.0.1:8001/snapshot/cam-01",
  last_frame_at: T,
  server_time: "2026-01-01T12:00:02Z",
  ...over,
})

const startedExecution = {
  id: "e9",
  station_id: "st-01",
  sop_key: "bottle_transfer",
  sop_version: 1,
  sop_content_hash: "abc123",
  status: "RUNNING",
  workpiece_id: null,
  started_at: T,
  finished_at: null,
  paused_at: null,
  total_paused_ms: 0,
  accept_events_until: "2026-01-01T12:10:00Z",
  steps: [],
  allowed_actions: ["ABORT"],
  server_time: "2026-01-01T12:00:02Z",
}

const sops = [
  {
    id: "sop-1",
    key: "bottle_transfer",
    name: "瓶体转移演示",
    created_at: T,
    latest_published_version_id: "sopv-demo-1",
    versions: [
      {
        id: "sopv-demo-1",
        sop_id: "sop-1",
        version: 1,
        status: "PUBLISHED",
        dsl_schema_version: "1.0",
        content_hash: "abc",
        created_at: T,
        published_at: T,
      },
    ],
  },
]

test.beforeEach(async ({ page }) => {
  await page.route("**/api/sops", (route) => route.fulfill({ json: sops }))
  await page.route("http://127.0.0.1:8001/**", (route) => route.abort())
})

test("starts an execution with the chosen published SOP version", async ({
  page,
}) => {
  await page.route("**/api/stations/st-01/runtime-state", (route) =>
    route.fulfill({ json: runtimeState({}) }),
  )
  await page.route("**/api/stations/st-01/executions", (route) =>
    route.fulfill({ status: 201, json: startedExecution }),
  )
  await page.route("**/api/executions/e9", (route) =>
    route.fulfill({ json: startedExecution }),
  )

  await page.goto("/stations/st-01")
  await expect(page.getByTestId("fact-process")).toContainText("暂无执行")

  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/stations/st-01/executions") &&
      request.method() === "POST",
  )
  await page.getByRole("button", { name: "开始执行" }).click()
  const request = await requestPromise
  expect(request.postDataJSON()).toEqual({ sop_version_id: "sopv-demo-1" })
  await expect(page).toHaveURL(/\/executions\/e9$/)
  await expect(page.getByTestId("fact-process")).toContainText(
    "SOP-bottle_transfer",
  )
})

test("offline camera keeps the four facts visible", async ({ page }) => {
  await page.route("**/api/stations/st-01/runtime-state", (route) =>
    route.fulfill({
      json: runtimeState({
        camera: {
          ...runtimeState({}).camera,
          health: "UNAVAILABLE",
          last_frame_at: null,
        },
        process_status: "OFFLINE",
        health: "UNAVAILABLE",
        last_frame_at: null,
      }),
    }),
  )

  await page.goto("/stations/st-01")
  await expect(page.getByText("无信号")).toBeVisible()
  await expect(page.getByTestId("fact-system")).toContainText("不可用")
  await expect(page.getByTestId("fact-process")).toBeVisible()
})
