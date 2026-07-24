import { expect, test } from "@playwright/test";

test("dashboard loads and shows the nav", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Nivesh AI")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Stocks" })).toBeVisible();
});
