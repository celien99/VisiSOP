import { expect, test } from "@playwright/test"

const T = "2026-01-01T12:00:00Z"

const alarm = {
  id: "alarm-1",
  execution_id: "e1",
  station_id: "st-01",
  camera_id: null,
  category: "PROCESS_COMPLIANCE",
  severity: "HIGH",
  status: "OPEN",
  reason_code: "TIMEOUT",
  step_key: "pick_bottle",
  message: "step timed out",
  first_seen_at: T,
  last_seen_at: T,
  occurrence_count: 2,
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
  comment: null,
}

const executions = [
  {
    id: "e1",
    sop_key: "bottle_transfer",
    sop_version: 1,
    status: "NEEDS_REVIEW",
    started_at: T,
    finished_at: null,
    current_step_key: "pick_bottle",
    current_step_name: "从取料区取起瓶体",
    current_step_status: "NEEDS_REVIEW",
  },
]

test.beforeEach(async ({ page }) => {
  await page.route("**/api/alarms*", (route) =>
    route.fulfill({ json: [alarm] }),
  )
  await page.route("**/api/executions", (route) =>
    route.fulfill({ json: executions }),
  )
})

test("records tabs and filters are URL-driven", async ({ page }) => {
  await page.goto("/records?tab=alarms&status=OPEN")
  await expect(page.getByRole("tab", { name: "告警" })).toHaveAttribute(
    "aria-selected",
    "true",
  )
  await expect(page.getByTestId("alarm-row")).toHaveCount(1)
  await expect(page.getByTestId("alarm-row")).toContainText("TIMEOUT")
})
