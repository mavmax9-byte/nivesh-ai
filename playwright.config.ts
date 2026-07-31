import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  // Serial, not parallel: these specs run against a live `next dev` server
  // (see README/CLAUDE context -- this repo has no CI-managed e2e stage),
  // and Next.js dev mode compiles each route on first request. Concurrent
  // first hits across many routes made cold-compile time indistinguishable
  // from a real failure; running serially keeps that latency out of the
  // test signal without touching app code.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
});
