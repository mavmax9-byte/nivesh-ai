import path from "node:path";

import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

// `output: "standalone"` only matters for `next build` -- it drives
// docker/frontend.Dockerfile's COPY of `.next/standalone` + `.next/static`
// (see docker-compose.yml's `frontend` service). It has no effect on `next dev`,
// but leaving it unconditional invites running `next build`/`next start` locally
// against the same `.next` directory `next dev` uses -- that mix once corrupted
// the dev cache badly enough to break the compiled CSS bundle. Scoping it to the
// production-build phase makes the intent explicit; see README's "Frontend
// Development Workflow" section for the recovery step (`npm run clean`) if this
// happens again.
const nextConfig = (phase: string): NextConfig => ({
  reactStrictMode: true,
  // Two lockfiles are intentional here, not a mistake to clean up: the repo-root
  // one pins Playwright's e2e-test dependency, this directory's own pins the
  // Next.js app's dependencies (consumed independently by
  // docker/frontend.Dockerfile). Pinning the workspace root explicitly silences
  // Next's multi-lockfile inference warning without deleting either lockfile.
  outputFileTracingRoot: path.join(__dirname),
  ...(phase === PHASE_PRODUCTION_BUILD ? { output: "standalone" as const } : {}),
});

export default nextConfig;
