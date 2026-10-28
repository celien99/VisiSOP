import { expect, test } from "@playwright/test"

test("renders the monitoring wall without demo data", async ({ page }) => {
  await page.goto("/")
  await expect(
    page.getByRole("heading", { name: "多机位监控墙" }),
  ).toBeVisible()
  await expect(page.getByText("Phase 1 不提供演示数据")).toBeVisible()
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible()
})

test("navigates between the wall, dashboard and records", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("link", { name: "看板" }).click()
  await expect(page.getByRole("heading", { name: "分析看板" })).toBeVisible()

  await page.getByRole("link", { name: "记录" }).click()
  await expect(page.getByRole("heading", { name: "记录" })).toBeVisible()
})
