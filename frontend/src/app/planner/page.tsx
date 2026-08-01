"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Wallet } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import { createPlannedPortfolio } from "@/lib/api/planner";
import { HORIZONS, RISK_PROFILES } from "@/lib/api/types";
import type { Horizon, RiskProfile } from "@/lib/api/types";

const SECTOR_EXCLUSION_OPTIONS = ["Technology", "Financials", "Energy", "Healthcare", "Consumer"];

export default function PlannerInputPage() {
  const router = useRouter();
  const [capital, setCapital] = useState("100000");
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [horizon, setHorizon] = useState<Horizon>("medium");
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  function toggleExclusion(sector: string) {
    setExclusions((prev) =>
      prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const capitalValue = Number(capital);
    if (!Number.isFinite(capitalValue) || capitalValue <= 0) {
      setError(new Error("Enter an investable amount greater than ₹0."));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const job = await createPlannedPortfolio({
        capital: capitalValue,
        risk_profile: riskProfile,
        horizon,
        sector_exclusions: exclusions,
      });
      router.push(`/planner/${job.id}`);
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <PageHeader
        eyebrow="Portfolio Planner"
        title="Build my portfolio"
        description="Tell us how much you're investing and your risk preference. We'll propose an illustrative, evidence-cited allocation across companies our Investment Committee has researched -- not a personalized recommendation to act on."
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <Card className="flex flex-col gap-2">
          <label htmlFor="capital" className="text-sm font-medium">
            Investable amount (₹)
          </label>
          <div className="relative">
            <Wallet
              size={16}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              id="capital"
              type="number"
              // No `min` attribute -- native HTML5 constraint validation
              // would block form submission (and our own onSubmit
              // handler) before it ever runs, silently swapping our
              // friendlier, branded error message for the browser's own
              // inconsistent native tooltip. handleSubmit's own check
              // below is the single source of truth for this validation.
              step="1"
              inputMode="decimal"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              className="pl-10"
              placeholder="100000"
            />
          </div>
        </Card>

        <Card className="flex flex-col gap-3">
          <span className="text-sm font-medium">Risk tolerance</span>
          <div className="grid gap-3 sm:grid-cols-3">
            {RISK_PROFILES.map((option) => (
              <button
                type="button"
                key={option.value}
                onClick={() => setRiskProfile(option.value)}
                className={`flex flex-col gap-1 rounded-lg border p-4 text-left transition-colors ${
                  riskProfile === option.value
                    ? "border-primary bg-accent"
                    : "border-border hover:bg-muted"
                }`}
              >
                <span className="text-sm font-semibold">{option.label}</span>
                <span className="text-xs text-muted-foreground">{option.description}</span>
              </button>
            ))}
          </div>
        </Card>

        <Card className="flex flex-col gap-3">
          <label htmlFor="horizon" className="text-sm font-medium">
            Investment horizon
          </label>
          <select
            id="horizon"
            value={horizon}
            onChange={(e) => setHorizon(e.target.value as Horizon)}
            className="flex h-11 w-full rounded-md border border-border bg-background px-3.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {HORIZONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Card>

        <Card className="flex flex-col gap-3">
          <span className="text-sm font-medium">
            Exclude sectors <span className="font-normal text-muted-foreground">(optional)</span>
          </span>
          <div className="flex flex-wrap gap-2">
            {SECTOR_EXCLUSION_OPTIONS.map((sector) => (
              <button
                type="button"
                key={sector}
                onClick={() => toggleExclusion(sector)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  exclusions.includes(sector)
                    ? "border-destructive/40 bg-destructive-bg text-destructive"
                    : "border-border bg-transparent hover:bg-muted"
                }`}
              >
                {sector}
              </button>
            ))}
          </div>
        </Card>

        {error ? (
          <Alert variant="destructive" title="Couldn't start portfolio generation">
            {error instanceof ApiError ? error.message : String((error as Error)?.message ?? error)}
          </Alert>
        ) : null}

        <Button type="submit" size="lg" disabled={submitting}>
          {submitting ? "Starting…" : "Generate my portfolio"}
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          Research only -- Nivesh AI never places, recommends, or executes trades. This is an
          illustrative allocation to evaluate, not personalized financial advice.
        </p>
      </form>
    </div>
  );
}
