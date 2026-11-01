import { expect, test } from "@playwright/test"

const T = "2026-01-01T12:00:00Z"

const project = {
  id: "p1",
  key: "remote",
  name: "遥控器装电池",
  classes: ["remote", "battery"],
  created_at: T,
}

const video = {
  id: "v1",
  project_id: "p1",
  filename: "clip.avi",
  status: "READY",
  duration_ms: 6000,
  fps: 10,
  frame_count: 2,
  error: null,
  created_at: T,
}

const frames = [
  {
    id: "f1",
    video_id: "v1",
    frame_index: 0,
    timestamp_ms: 0,
    width: 320,
    height: 240,
    image_url: "/api/training/frames/f1",
    thumb_url: "/api/training/frames/f1/thumb",
    annotation_count: 0,
  },
  {
    id: "f2",
    video_id: "v1",
    frame_index: 1,
    timestamp_ms: 500,
    width: 320,
    height: 240,
    image_url: "/api/training/frames/f2",
    thumb_url: "/api/training/frames/f2/thumb",
    annotation_count: 1,
  },
]

const dataset = {
  id: "d1",
  version: 1,
  frame_count: 2,
  train_count: 1,
  val_count: 1,
  storage_key: "projects/remote/datasets/v1",
  created_at: T,
}

const job = {
  id: "j1",
  project_id: "p1",
  dataset_version_id: "d1",
  status: "QUEUED",
  progress: 0,
  epochs: 10,
  metrics: {},
  error: null,
  created_at: T,
  started_at: null,
  finished_at: null,
}

const model = {
  id: "m1",
  project_id: "p1",
  version: 1,
  training_job_id: "j1",
  metrics: { mAP50: 0.9 },
  manifest: {},
  active: false,
  created_at: T,
  artifact_url: "/api/training/models/m1/artifact",
  names_url: "/api/training/models/m1/names",
}

const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#202020"/></svg>'

test.beforeEach(async ({ page }) => {
  await page.route("**/api/training/projects", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: { ...project, id: "p2" } })
      : route.fulfill({ json: [project] }),
  )
  await page.route("**/api/training/projects/p1/videos", (route) =>
    route.fulfill({ json: [video] }),
  )
  await page.route("**/api/training/videos/v1/frames", (route) =>
    route.fulfill({ json: frames }),
  )
  await page.route("**/api/training/frames/f1/annotations", (route) =>
    route.request().method() === "PUT"
      ? route.fulfill({ json: [] })
      : route.fulfill({ json: [] }),
  )
  await page.route("**/api/training/frames/f1", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: svg }),
  )
  await page.route("**/api/training/frames/f1/thumb", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: svg }),
  )
  await page.route("**/api/training/frames/f2/thumb", (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: svg }),
  )
  await page.route("**/api/training/projects/p1/stats", (route) =>
    route.fulfill({
      json: {
        videos: 1,
        frames: 2,
        labeled_frames: 1,
        annotations: 1,
        per_class: { remote: 1 },
      },
    }),
  )
  await page.route("**/api/training/projects/p1/datasets", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: dataset })
      : route.fulfill({ json: [dataset] }),
  )
  await page.route("**/api/training/projects/p1/jobs", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: job })
      : route.fulfill({ json: [] }),
  )
  await page.route("**/api/training/projects/p1/models", (route) =>
    route.fulfill({ json: [model] }),
  )
  await page.route("**/api/training/models/m1/activate", (route) =>
    route.fulfill({
      json: { ...model, active: true },
    }),
  )
})

test("labelling a frame sends normalized boxes", async ({ page }) => {
  await page.goto("/training")
  await expect(page.getByText("遥控器装电池")).toBeVisible()
  await page.getByRole("button", { name: /帧 0/ }).click()

  const canvas = page.locator(".vs-labeler__canvas")
  const box = await canvas.boundingBox()
  if (!box) throw new Error("canvas missing")
  await page.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.1)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6)
  await page.mouse.up()

  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().includes("/frames/f1/annotations") &&
      request.method() === "PUT",
  )
  await page.getByRole("button", { name: "保存标注" }).click()
  const request = await requestPromise
  const payload = request.postDataJSON() as {
    annotations: Array<{ class_name: string; x1: number; x2: number }>
  }
  expect(payload.annotations).toHaveLength(1)
  expect(payload.annotations[0].class_name).toBe("remote")
  expect(payload.annotations[0].x2).toBeGreaterThan(payload.annotations[0].x1)
})

test("starting a job uses the selected dataset", async ({ page }) => {
  await page.goto("/training")
  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().includes("/api/training/projects/p1/jobs") &&
      request.method() === "POST",
  )
  await page.getByRole("button", { name: "开始训练" }).click()
  const request = await requestPromise
  expect(request.postDataJSON()).toMatchObject({
    dataset_version_id: "d1",
    epochs: 50,
  })
})

test("activation requires an operator", async ({ page }) => {
  await page.goto("/training")
  const activate = page.getByRole("button", { name: "激活" })
  await expect(activate).toBeDisabled()
  await page.getByLabel("激活操作者").fill("tester")
  await expect(activate).toBeEnabled()
  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().includes("/activate") && request.method() === "POST",
  )
  await activate.click()
  const request = await requestPromise
  expect(request.postDataJSON()).toEqual({ operator: "tester" })
})
