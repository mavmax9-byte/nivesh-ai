import { expect, test } from "@playwright/test";

test("landing page loads and shows primary navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Nivesh AI").first()).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /evidence-backed equity research/i }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Companies", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /search a company/i }).first()).toBeVisible();
});

test("landing page CTA navigates to company search", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /search a company/i }).first().click();
  await expect(page).toHaveURL(/\/companies$/);
  await expect(page.getByRole("heading", { name: "Company search" })).toBeVisible();
});
