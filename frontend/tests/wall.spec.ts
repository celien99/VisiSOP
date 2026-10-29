import { expect, test } from "@playwright/test"

const state = (over: Record<string, unknown>) => ({
  station: {
    id: "st-01",
    code: "ST-01",
    name: "演示工位",
    zone: "A",
    created_at: "2026-01-01T12:00:00Z",
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
    last_frame_at: "2026-01-01T12:00:01Z",
    created_at: "2026-01-01T12:00:00Z",
  },
  execution: {
    id: "e1",
    sop_key: "bottle_transfer",
    sop_version: 1,
    status: "RUNNING",
    started_at: "2026-01-01T12:00:00Z",
    finished_at: null,
    current_step_key: "pick_bottle",
    current_step_name: "从取料区取起瓶体",
    current_step_status: "ACTIVE",
  },
  steps: [
    {
      key: "pick_bottle",
      name: "从取料区取起瓶体",
      status: "ACTIVE",
      reason_code: null,
      started_at: "2026-01-01T12:00:00Z",
    },
    {
      key: "place_bottle",
      name: "将瓶体放入目标区",
      status: "PENDING",
      reason_code: null,
      started_at: null,
    },
  ],
  process_status: "RUNNING",
  attention_since: null,
  open_alarm_count: 0,
  highest_alarm_severity: null,
  health: "HEALTHY",
  preview_url: "http://127.0.0.1:8001/stream/cam-01",
  snapshot_url: "http://127.0.0.1:8001/snapshot/cam-01",
  last_frame_at: "2026-01-01T12:00:01Z",
  server_time: "2026-01-01T12:00:02Z",
  ...over,
})

test.beforeEach(async ({ page }) => {
  await page.route("**/api/stations/runtime-state", (route) =>
    route.fulfill({
      json: [
        state({}),
        state({
          station: {
            ...state({}).station,
            id: "st-02",
            code: "ST-02",
            name: "工位二",
          },
          process_status: "REVIEW",
          attention_since: "2026-01-01T11:59:00Z",
          steps: [
            {
              key: "pick_bottle",
              name: "从取料区取起瓶体",
              status: "NEEDS_REVIEW",
              reason_code: "EVIDENCE_MISSING",
              started_at: null,
            },
          ],
          execution: {
            ...state({}).execution,
            id: "e2",
            status: "NEEDS_REVIEW",
          },
        }),
      ],
    }),
  )
  await page.route("http://127.0.0.1:8001/**", (route) => route.abort())
})

test("renders one card per station and separates review from offline", async ({
  page,
}) => {
  await page.goto("/")
  await expect(page.getByTestId("wall-card")).toHaveCount(2)
  await expect(page.getByTestId("wall-card").nth(1)).toContainText("待复核")
  await expect(page.getByTestId("attention-strip")).toContainText("ST-02")
})

test("attention filter is URL-driven", async ({ page }) => {
  await page.goto("/?attention=1")
  await expect(page.getByTestId("wall-card")).toHaveCount(1)
  await expect(page.getByTestId("wall-card")).toContainText("ST-02")
})

test("a dead preview does not hide process facts", async ({ page }) => {
  await page.goto("/")
  const card = page.getByTestId("wall-card").first()
  await expect(card).toContainText("预览不可用")
  await expect(card).toContainText("从取料区取起瓶体")
  await expect(card).toContainText("执行中")
})

test("card links to the station", async ({ page }) => {
  await page.goto("/")
  await page.getByTestId("wall-card").first().click()
  await expect(page).toHaveURL(/\/stations\/st-01$/)
})

test("an offline camera is a distinct state, not an error", async ({
  page,
}) => {
  await page.route("**/api/stations/runtime-state", (route) =>
    route.fulfill({
      json: [
        state({
          camera: {
            ...state({}).camera,
            health: "UNAVAILABLE",
            last_frame_at: null,
          },
          process_status: "OFFLINE",
          health: "UNAVAILABLE",
          last_frame_at: null,
        }),
      ],
    }),
  )
  await page.goto("/")
  const card = page.getByTestId("wall-card").first()
  await expect(card).toContainText("离线")
  await expect(card).toContainText("无信号")
  await expect(card).toContainText("从取料区取起瓶体")
})

test("a healthy camera with an old frame is not labelled live", async ({
  page,
}) => {
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "base64",
  )
  await page.route("http://127.0.0.1:8001/**", (route) =>
    route.fulfill({ body: png, contentType: "image/png" }),
  )
  await page.route("**/api/stations/runtime-state", (route) =>
    route.fulfill({
      json: [
        state({
          last_frame_at: "2026-01-01T11:59:45Z",
          server_time: "2026-01-01T12:00:02Z",
        }),
      ],
    }),
  )
  await page.goto("/")
  const card = page.getByTestId("wall-card").first()
  await expect(card).toContainText("最后一帧")
  await expect(card).not.toContainText("实时预览")
})
