import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.route("**/api/stations/runtime-state", (route) =>
    route.fulfill({ json: [] }),
  )
})

test("the wall explains why it is empty instead of showing fake data", async ({
  page,
}) => {
  await page.goto("/")
  await expect(
    page.getByRole("heading", { name: "多机位监控墙" }),
  ).toBeVisible()
  await expect(page.getByText("暂无已配置工位")).toBeVisible()
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible()
})

test("navigates between the wall, dashboard and records", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("link", { name: "看板" }).click()
  await expect(page.getByRole("heading", { name: "分析看板" })).toBeVisible()

  await page.getByRole("link", { name: "记录" }).click()
  await expect(page.getByRole("heading", { name: "记录" })).toBeVisible()
})
