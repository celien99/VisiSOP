import { expect, test } from "@playwright/test"

test("the shell exposes connection state without fake data", async ({
  page,
}) => {
  await page.goto("/")
  const indicator = page.getByTestId("connection-indicator")
  await expect(indicator).toBeVisible()
  await expect(indicator).toContainText(/已连接|连接中|连接中断/)
  await expect(page.getByRole("banner")).toBeVisible()
})
