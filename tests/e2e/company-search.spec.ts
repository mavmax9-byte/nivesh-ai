import { expect, test } from "@playwright/test";

test("company search page lists real companies from the backend", async ({ page }) => {
  await page.goto("/companies");
  await expect(page.getByRole("heading", { name: "Company search" })).toBeVisible();

  // Either real companies are listed, or the empty state explains none exist
  // yet -- both are valid backend states, never a client-side crash.
  const emptyState = page.getByText("No companies yet");
  const companyCount = page.getByText(/compan(y|ies)$/);
  await expect(emptyState.or(companyCount)).toBeVisible({ timeout: 15_000 });
});

test("search input filters the company list client-side", async ({ page }) => {
  await page.goto("/companies");
  const searchInput = page.getByPlaceholder(/search by symbol/i);
  await expect(searchInput).toBeVisible();

  await searchInput.fill("zzzznonexistentsymbolzzzz");
  await expect(page.getByText("No matches")).toBeVisible();
});

test("unknown company symbol shows a clear not-found state", async ({ page }) => {
  await page.goto("/companies/THISCOMPANYDOESNOTEXIST");
  await expect(page.getByText(/no company found/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /back to search/i })).toBeVisible();
});
