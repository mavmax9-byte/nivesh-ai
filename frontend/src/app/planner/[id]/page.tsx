"use client";

import { use, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, RefreshCw } from "lucide-react";

import { HoldingCard } from "@/components/planner/HoldingCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { usePolling } from "@/hooks/usePolling";
import { getRebalanceSuggestion, pollPlannedPortfolio } from "@/lib/api/planner";
import type { PlannedPortfolio } from "@/lib/api/types";
import { useAsync } from "@/hooks/useAsync";

function formatCurrency(value: number): string {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export default function PlannedPortfolioPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const polling = usePolling<PlannedPortfolio | null>(() => pollPlannedPortfolio(id), {
    intervalMs: 3000,
    stopWhen: (portfolio) => portfolio === null || portfolio.status !== "generating",
  });

  const portfolio = polling.data;

  if (polling.loading && !portfolio) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-20 rounded-lg" />
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );
  }

  if (polling.error) {
    return <ErrorState error={polling.error} />;
  }

  if (portfolio === null) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="font-medium">No portfolio found for this link.</p>
        <Link href="/planner" className={cn(buttonVariants({ variant: "outline" }))}>
          Build a new portfolio
        </Link>
      </div>
    );
  }

  if (portfolio.status === "generating") {
    return <GeneratingView elapsedMs={polling.elapsedMs} />;
  }

  if (portfolio.status === "failed") {
    return <FailedView portfolio={portfolio} />;
  }

  return <ReviewView portfolio={portfolio} />;
}

function GeneratingView({ elapsedMs }: { elapsedMs: number }) {
  const elapsedSeconds = Math.round(elapsedMs / 1000);
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-4 py-20 text-center">
      <Loader2 size={28} className="animate-spin text-primary" />
      <p className="font-medium">Building your portfolio…</p>
      <p className="text-sm text-muted-foreground">
        Screening the research universe, generating any missing Investment Committee reports, and
        computing an evidence-weighted allocation. This can take a few minutes for the first run.
      </p>
      <p className="text-xs text-muted-foreground">
        {elapsedSeconds > 0 ? `${elapsedSeconds}s elapsed` : "Starting…"}
      </p>
    </div>
  );
}

function FailedView({ portfolio }: { portfolio: PlannedPortfolio }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 py-16">
      <div className="flex flex-col items-center gap-3 text-center">
        <AlertTriangle size={28} className="text-destructive" />
        <p className="font-medium">Couldn&apos;t build a portfolio</p>
      </div>
      <Alert variant="destructive">
        {portfolio.failure_reason ?? "Something went wrong generating this portfolio."}
      </Alert>
      <Link href="/planner" className={cn(buttonVariants({ variant: "outline" }), "self-center")}>
        Try different inputs
      </Link>
    </div>
  );
}

function ReviewView({ portfolio }: { portfolio: PlannedPortfolio }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Portfolio Planner"
        title="Your illustrative portfolio"
        description={`Generated ${new Date(portfolio.updated_at).toLocaleString("en-IN", {
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })} · ${portfolio.holdings.length} holding${portfolio.holdings.length === 1 ? "" : "s"}`}
        actions={
          <Link href="/planner" className={cn(buttonVariants({ variant: "outline" }), "gap-2")}>
            <ArrowLeft size={15} />
            New plan
          </Link>
        }
      />

      <Alert variant="warning" title="This is not personalized investment advice">
        An illustrative, evidence-cited allocation for {formatCurrency(portfolio.capital)} based on
        real Investment Committee research -- not a directive to buy or sell. Nivesh AI never places,
        recommends, or executes trades. Consult a registered investment advisor before acting.
      </Alert>

      <Card className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Capital" value={formatCurrency(portfolio.capital)} />
          <Stat label="Allocated" value={formatCurrency(portfolio.capital - (portfolio.unallocated_amount ?? 0))} />
          <Stat
            label="Confidence"
            value={
              portfolio.confidence_score !== null
                ? `${Math.round(portfolio.confidence_score * 100)}%`
                : "—"
            }
          />
          <Stat label="Universe" value={`${portfolio.universe_size ?? "—"} companies`} />
        </div>
        {portfolio.summary ? (
          <p className="border-t border-border pt-4 text-sm text-muted-foreground">
            {portfolio.summary}
          </p>
        ) : null}
      </Card>

      {portfolio.caveats.length > 0 ? (
        <Alert variant="info" title="Worth knowing">
          <ul className="list-disc space-y-1 pl-4">
            {portfolio.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Holdings</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {portfolio.holdings.map((holding) => (
            <HoldingCard key={holding.company_id} holding={holding} />
          ))}
        </div>
        {portfolio.holdings.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No holdings could be allocated for this plan.
          </p>
        ) : null}
      </div>

      <RebalanceSection portfolioId={portfolio.id} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function RebalanceSection({ portfolioId }: { portfolioId: string }) {
  const [checked, setChecked] = useState(false);
  // `useAsync`'s deps array must stay a *constant length* across renders
  // (a React Rules-of-Hooks requirement) -- gating with `checked ? [a, b]
  // : []` violated that (found via a live console error during v1.1
  // verification) and, separately, still fired the real network call on
  // mount regardless of `checked` (deps only control *re-fetching*, not
  // the initial mount fetch). Fixed by keeping deps constant-length and
  // gating the actual API call inside the fetcher itself.
  const rebalance = useAsync(async () => {
    if (!checked) return null;
    return await getRebalanceSuggestion(portfolioId);
  }, [portfolioId, checked]);

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <RefreshCw size={16} className="text-muted-foreground" />
        <h2 className="font-semibold">Rebalancing</h2>
      </div>
      {!checked ? (
        <button
          type="button"
          onClick={() => setChecked(true)}
          className="self-start text-sm font-medium text-primary hover:underline"
        >
          Check for rebalancing suggestions →
        </button>
      ) : rebalance.loading ? (
        <Skeleton className="h-5 w-2/3" />
      ) : (
        <p className="text-sm text-muted-foreground">
          {rebalance.data?.message ?? "Rebalancing suggestions are not yet available."}
        </p>
      )}
    </Card>
  );
}
