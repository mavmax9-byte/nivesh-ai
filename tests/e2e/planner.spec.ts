import { expect, test } from "@playwright/test";

// TCS is the canonical real company used throughout this project's own
// backend verification history -- it's the one company in this
// environment with sufficient data to be a candidate for the planner's
// universe selection (see PROJECT_CONTEXT.md / INVESTMENT_PLANNER_DESIGN.md).

test("landing page links to the portfolio planner", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /build my portfolio/i }).click();
  await expect(page).toHaveURL(/\/planner$/);
  await expect(page.getByRole("heading", { name: "Build my portfolio" })).toBeVisible();
});

test("planner input screen renders capital, risk profile, and horizon controls", async ({
  page,
}) => {
  await page.goto("/planner");
  await expect(page.getByLabel("Investable amount (₹)")).toBeVisible();
  // Anchored regexes, not plain strings: each risk-profile button's
  // accessible name concatenates its label + description, and "growth"
  // appears inside Balanced's own description text ("...stability and
  // growth..."), so a bare substring match for "Growth" ambiguously
  // matches both buttons.
  await expect(page.getByRole("button", { name: /^Conservative/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Balanced/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Growth/ })).toBeVisible();
  await expect(page.getByLabel("Investment horizon")).toBeVisible();
  await expect(page.getByRole("button", { name: /generate my portfolio/i })).toBeVisible();
});

test("submitting a non-positive capital shows a client-side error, not a request", async ({
  page,
}) => {
  await page.goto("/planner");
  await page.getByLabel("Investable amount (₹)").fill("0");
  await page.getByRole("button", { name: /generate my portfolio/i }).click();
  await expect(page.getByText(/enter an investable amount/i)).toBeVisible();
  // Still on the input screen -- no navigation happened.
  await expect(page).toHaveURL(/\/planner$/);
});

test("generating a portfolio reaches a ready or failed terminal state against the real pipeline", async ({
  page,
}) => {
  await page.goto("/planner");
  await page.getByLabel("Investable amount (₹)").fill("100000");
  await page.getByRole("button", { name: "Balanced" }).click();
  await page.getByRole("button", { name: /generate my portfolio/i }).click();

  await expect(page).toHaveURL(/\/planner\/[0-9a-f-]{36}$/, { timeout: 15_000 });

  const ready = page.getByRole("heading", { name: "Your illustrative portfolio" });
  const failed = page.getByText("Couldn't build a portfolio");
  await expect(ready.or(failed)).toBeVisible({ timeout: 60_000 });
});

test("a ready portfolio shows the non-advice disclaimer, holdings, and a working rebalance check", async ({
  page,
}) => {
  await page.goto("/planner");
  await page.getByLabel("Investable amount (₹)").fill("100000");
  await page.getByRole("button", { name: "Balanced" }).click();
  await page.getByRole("button", { name: /generate my portfolio/i }).click();
  await expect(page).toHaveURL(/\/planner\/[0-9a-f-]{36}$/, { timeout: 15_000 });

  const ready = page.getByRole("heading", { name: "Your illustrative portfolio" });
  const failed = page.getByText("Couldn't build a portfolio");
  await expect(ready.or(failed)).toBeVisible({ timeout: 60_000 });

  if (await failed.isVisible().catch(() => false)) {
    test.skip(true, "No eligible candidate produced a portfolio in this environment right now");
  }

  await expect(page.getByText(/not personalized investment advice/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Holdings" })).toBeVisible();

  await page.getByRole("button", { name: /check for rebalancing suggestions/i }).click();
  await expect(page.getByText(/not yet available/i)).toBeVisible();
});

test("an unknown portfolio id shows a clear not-found state, not a crash", async ({ page }) => {
  await page.goto("/planner/00000000-0000-0000-0000-000000000000");
  await expect(page.getByText(/no portfolio found for this link/i)).toBeVisible();
  await page.getByRole("link", { name: /build a new portfolio/i }).click();
  await expect(page).toHaveURL(/\/planner$/);
});
