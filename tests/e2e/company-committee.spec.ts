import { expect, test } from "@playwright/test";

// TCS is the canonical real company used throughout this project's own
// backend verification history -- these specs assume it exists in
// whatever backend the frontend is pointed at (see PROJECT_CONTEXT.md).
const SYMBOL = "TCS";

test("company hub renders the profile and sub-navigation for a real company", async ({ page }) => {
  await page.goto(`/companies/${SYMBOL}`);
  await expect(page.getByRole("heading", { name: SYMBOL, exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Research Report" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Specialist Findings" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Evidence/ })).toBeVisible();

  // Either a generated committee report, or the CTA to make one --
  // never a blank page or an unhandled error.
  const ready = page.getByText("Committee report ready");
  const cta = page.getByRole("button", { name: /generate investment committee report/i });
  await expect(ready.or(cta)).toBeVisible({ timeout: 15_000 });
});

test("specialist findings page lists all five specialists", async ({ page }) => {
  await page.goto(`/companies/${SYMBOL}/specialists`);
  await expect(page.getByText("Fundamental Analyst")).toBeVisible();
  await expect(page.getByText("Technical Analyst")).toBeVisible();
  await expect(page.getByText("Valuation Analyst")).toBeVisible();
  await expect(page.getByText("News & Sentiment Analyst")).toBeVisible();
  await expect(page.getByText("Risk Analyst")).toBeVisible();
});

test("unknown specialist slug shows a clear error, not a crash", async ({ page }) => {
  await page.goto(`/companies/${SYMBOL}/specialists/not-a-real-specialist`);
  await expect(page.getByText("Unknown specialist")).toBeVisible();
});

test("evidence page is reachable from the report via citation links", async ({ page }) => {
  await page.goto(`/companies/${SYMBOL}/report`);

  const noReportYet = page.getByText("No research report yet");
  if (await noReportYet.isVisible().catch(() => false)) {
    test.skip(true, "No committee report generated yet for this company in this environment");
  }

  await expect(page.getByRole("heading", { name: /Research Report/ })).toBeVisible();
  await page.getByRole("link", { name: /view all evidence/i }).click();
  await expect(page).toHaveURL(new RegExp(`/companies/${SYMBOL}/evidence$`));
  await expect(page.getByRole("heading", { name: /Evidence & citations/i })).toBeVisible();
});
