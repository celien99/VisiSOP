import { expect, test } from "@playwright/test"

const T = "2026-01-01T12:00:00Z"

const dsl = {
  schema_version: "1.0",
  sop_key: "bottle_transfer",
  version: 1,
  name: "瓶体转移演示",
  steps: [
    {
      key: "pick_bottle",
      name: "从取料区取起瓶体",
      type: "ACTION",
      timeout_ms: 60000,
      completion: {
        mode: "EVENT_RULE",
        all: [{ event_type: "bottle_in_pickup_zone" }],
      },
      evidence: { required: true, kind: "keyframe" },
    },
  ],
}

const steps = [
  {
    key: "pick_bottle",
    name: "从取料区取起瓶体",
    type: "ACTION",
    required: true,
    depends_on: [],
  },
]

const draftV2 = {
  id: "v2",
  sop_id: "sop-1",
  version: 2,
  status: "DRAFT",
  dsl_schema_version: "1.0",
  content_hash: "hash-two",
  created_at: T,
  published_at: null,
  dsl: { ...dsl, version: 2 },
  steps,
}

const publishedV1 = {
  id: "v1",
  sop_id: "sop-1",
  version: 1,
  status: "PUBLISHED",
  dsl_schema_version: "1.0",
  content_hash: "hash-one",
  created_at: T,
  published_at: T,
  dsl,
  steps,
}

const detail = {
  id: "sop-1",
  key: "bottle_transfer",
  name: "瓶体转移演示",
  created_at: T,
  latest_published_version_id: "v1",
  versions: [draftV2, publishedV1],
}

const summary = (version: typeof draftV2 | typeof publishedV1) => ({
  id: version.id,
  sop_id: version.sop_id,
  version: version.version,
  status: version.status,
  dsl_schema_version: version.dsl_schema_version,
  content_hash: version.content_hash,
  created_at: version.created_at,
  published_at: version.published_at,
})

const list = [
  {
    id: "sop-1",
    key: "bottle_transfer",
    name: "瓶体转移演示",
    created_at: T,
    latest_published_version_id: "v1",
    versions: [summary(draftV2), summary(publishedV1)],
  },
]

test.beforeEach(async ({ page }) => {
  await page.route("**/api/sops", (route) => route.fulfill({ json: list }))
  await page.route("**/api/sops/sop-1/validate", (route) =>
    route.fulfill({
      json: {
        valid: false,
        issues: [
          {
            code: "UNKNOWN_EVENT_TYPE",
            message: "未注册的事件类型",
            step_key: "pick_bottle",
          },
        ],
      },
    }),
  )
  await page.route("**/api/sops/sop-1/publish", (route) =>
    route.fulfill({ json: { ...publishedV1, id: "v2", version: 2 } }),
  )
  await page.route("**/api/sops/sop-1", (route) =>
    route.fulfill({
      json: route.request().method() === "PATCH" ? draftV2 : detail,
    }),
  )
})

test("invalid DSL blocks validate and publish", async ({ page }) => {
  await page.goto("/sops")
  await page.getByLabel("DSL JSON").fill("{ not json")
  await page.getByRole("button", { name: "验证" }).click()
  await expect(page.getByText("DSL 不是合法 JSON")).toBeVisible()
  await expect(page.getByRole("button", { name: "发布" })).toBeDisabled()
})

test("API validation issues are shown and publish is disabled", async ({
  page,
}) => {
  await page.goto("/sops")
  await page.getByRole("button", { name: "验证" }).click()
  await expect(page.getByText("UNKNOWN_EVENT_TYPE")).toBeVisible()
  await expect(page.getByRole("button", { name: "发布" })).toBeDisabled()
})

test("a valid validation allows the confirmed publish", async ({ page }) => {
  await page.route("**/api/sops/sop-1/validate", (route) =>
    route.fulfill({ json: { valid: true, issues: [] } }),
  )
  await page.goto("/sops")
  await page.getByRole("button", { name: "验证" }).click()
  await expect(page.getByText("校验通过")).toBeVisible()
  await page.getByRole("button", { name: "发布" }).click()
  await expect(page.getByRole("dialog")).toContainText("v2")
  await page.getByRole("button", { name: "确认发布" }).click()
  await expect(page.getByText("已发布")).toBeVisible()
})
