import { expect, test } from "@playwright/test"

const T = "2026-01-01T12:00:00Z"

const execution = {
  id: "e1",
  station_id: "st-01",
  sop_key: "bottle_transfer",
  sop_version: 1,
  sop_content_hash: "abc123def4567890",
  status: "NEEDS_REVIEW",
  workpiece_id: null,
  started_at: T,
  finished_at: null,
  paused_at: null,
  total_paused_ms: 0,
  accept_events_until: "2026-01-01T12:10:00Z",
  steps: [
    {
      key: "pick_bottle",
      name: "从取料区取起瓶体",
      type: "ACTION",
      required: true,
      status: "NEEDS_REVIEW",
      reason_code: "EVIDENCE_MISSING",
      activated_at: T,
      deadline_at: "2026-01-01T12:01:00Z",
      matched_events: [],
      evidence: [
        {
          id: "ev-1",
          event_id: "evt-1",
          status: "PENDING_VERIFY",
          url: "/api/evidence/ev-1",
          sha256: "ab",
          width: 64,
          height: 48,
          created_at: T,
        },
      ],
      skipped_reason: null,
      review_reason: null,
      review_comment: null,
      reviewed_by: null,
      reviewed_at: null,
      allowed_actions: ["REVIEW"],
    },
    {
      key: "place_bottle",
      name: "将瓶体放入目标区",
      type: "ACTION",
      required: true,
      status: "PENDING",
      reason_code: null,
      activated_at: null,
      deadline_at: null,
      matched_events: [],
      evidence: [],
      skipped_reason: null,
      review_reason: null,
      review_comment: null,
      reviewed_by: null,
      reviewed_at: null,
      allowed_actions: [],
    },
  ],
  allowed_actions: ["ABORT"],
  server_time: "2026-01-01T12:00:02Z",
}

const timeline = [
  {
    type: "EVENT",
    at: T,
    title: "bottle_in_pickup_zone",
    detail: null,
    step_key: "pick_bottle",
    reason_code: null,
    event_type: "bottle_in_pickup_zone",
    confidence: 0.9,
    model: "yolo11n v1",
  },
  {
    type: "ALARM",
    at: "2026-01-01T12:00:01Z",
    title: "证据缺失",
    detail: null,
    step_key: "pick_bottle",
    reason_code: "EVIDENCE_MISSING",
    event_type: null,
    confidence: null,
    model: null,
  },
]

const system = {
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
    preview_url: null,
    snapshot_url: null,
    health: "HEALTHY",
    last_frame_at: T,
    created_at: T,
  },
  execution: null,
  steps: [],
  process_status: "REVIEW",
  attention_since: null,
  open_alarm_count: 0,
  highest_alarm_severity: null,
  health: "HEALTHY",
  preview_url: null,
  snapshot_url: null,
  last_frame_at: T,
  server_time: "2026-01-01T12:00:02Z",
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/executions/e1/timeline", (route) =>
    route.fulfill({ json: timeline }),
  )
  await page.route("**/api/executions/e1", (route) =>
    route.fulfill({ json: execution }),
  )
  await page.route("**/api/stations/st-01/runtime-state", (route) =>
    route.fulfill({ json: system }),
  )
  await page.route("**/api/executions/e1/steps/*/review", (route) =>
    route.fulfill({ status: 200, json: {} }),
  )
  await page.route("**/api/evidence/**", (route) => route.abort())
})

test("review is offered only for NEEDS_REVIEW and sends the operator and reason", async ({
  page,
}) => {
  await page.goto("/executions/e1")
  await expect(page.getByTestId("fact-process")).toContainText("待复核")
  await expect(page.getByRole("button", { name: "复核" })).toHaveCount(1)

  await page.getByRole("button", { name: "复核" }).click()
  await page.getByLabel("操作者").fill("tester")
  await page.getByLabel("理由").fill("人工确认放置完成")
  await page.getByLabel("标记完成").check()

  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().includes("/review") && request.method() === "POST",
  )
  await page.getByRole("button", { name: "提交复核" }).click()
  const request = await requestPromise
  expect(request.postDataJSON()).toMatchObject({
    operator: "tester",
    reason: "人工确认放置完成",
    decision: "MARK_COMPLETED",
  })
})

test("unverified evidence is explicitly unavailable", async ({ page }) => {
  await page.goto("/executions/e1")
  await expect(page.getByTestId("fact-evidence")).toContainText("待校验")
  await expect(page.getByTestId("evidence-thumb").first()).toHaveAttribute(
    "aria-disabled",
    "true",
  )
})
