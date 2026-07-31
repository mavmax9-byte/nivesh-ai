"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, FileSearch, Sparkles } from "lucide-react";

import { CompanyProfileCard } from "@/components/companies/CompanyProfileCard";
import { CompanySubNav } from "@/components/companies/CompanySubNav";
import { ComplianceBadge } from "@/components/committee/ComplianceBadge";
import { ConfidenceMeter } from "@/components/committee/ConfidenceMeter";
import { SpecialistStatusRow } from "@/components/committee/SpecialistStatusRow";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { usePolling } from "@/hooks/usePolling";
import { getCompany } from "@/lib/api/companies";
import { pollResearchDossier } from "@/lib/api/research";
import { pollCommitteeProgress, requestCommitteeReport } from "@/lib/api/reports";
import { ApiError } from "@/lib/api-client";
import { SPECIALISTS } from "@/lib/api/types";
import type { CommitteeProgressSnapshot } from "@/lib/api/reports";

export default function CompanyHubPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: rawSymbol } = use(params);
  const symbol = rawSymbol.toUpperCase();

  const company = useAsync(() => getCompany(symbol), [symbol]);
  const dossier = useAsync(() => pollResearchDossier(symbol), [symbol]);

  const initialProgress = useAsync(() => pollCommitteeProgress(symbol), [symbol]);
  const [watching, setWatching] = useState(false);
  const [triggerError, setTriggerError] = useState<unknown>(null);
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    if (!initialProgress.loading && initialProgress.data) {
      const hasProgress =
        initialProgress.data.report !== null ||
        initialProgress.data.specialists.some((s) => s.finding !== null);
      if (hasProgress) setWatching(true);
    }
  }, [initialProgress.loading, initialProgress.data]);

  const polling = usePolling<CommitteeProgressSnapshot>(() => pollCommitteeProgress(symbol), {
    enabled: watching,
    intervalMs: 4000,
    stopWhen: (snapshot) => snapshot.report !== null,
  });

  const snapshot = polling.data ?? initialProgress.data;

  async function handleGenerate() {
    if (!company.data) return;
    setTriggerError(null);
    setTriggering(true);
    try {
      await requestCommitteeReport(company.data.id);
      setWatching(true);
    } catch (err) {
      setTriggerError(err);
    } finally {
      setTriggering(false);
    }
  }

  if (company.loading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-24 rounded-lg" />
        <Skeleton className="h-40 rounded-lg" />
      </div>
    );
  }

  if (company.notFound) {
    return (
      <EmptyState
        icon={FileSearch}
        title={`No company found for "${symbol}"`}
        description="Double-check the symbol, or search the research index."
        action={
          <Link href="/companies" className="text-sm font-medium text-primary hover:underline">
            ← Back to search
          </Link>
        }
      />
    );
  }

  if (company.error) {
    return <ErrorState error={company.error} onRetry={company.refetch} />;
  }

  if (!company.data) return null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Company" title={company.data.symbol} />

      <CompanyProfileCard company={company.data} dossier={dossier.data ?? null} />

      <CompanySubNav symbol={symbol} active={`/companies/${symbol}`} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles size={17} className="text-primary" />
            Investment Committee
          </CardTitle>
        </CardHeader>
        <CardContent>
          {initialProgress.loading && !snapshot ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-1/2" />
            </div>
          ) : initialProgress.error && !initialProgress.notFound ? (
            <ErrorState error={initialProgress.error} onRetry={initialProgress.refetch} />
          ) : snapshot?.report ? (
            <ReadyPanel symbol={symbol} snapshot={snapshot} />
          ) : watching ? (
            <GeneratingPanel snapshot={snapshot} elapsedMs={polling.elapsedMs} />
          ) : (
            <GeneratePanel
              symbol={symbol}
              onGenerate={handleGenerate}
              triggering={triggering}
              error={triggerError}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function GeneratePanel({
  onGenerate,
  triggering,
  error,
}: {
  symbol: string;
  onGenerate: () => void;
  triggering: boolean;
  error: unknown;
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        No committee report exists yet for this company. Generating one runs all five specialist
        agents over a shared pool of real evidence, synthesizes their findings, and gates the
        result through a deterministic compliance check -- typically a few minutes.
      </p>
      {error ? (
        <Alert variant="destructive" title="Couldn't start the committee run">
          {error instanceof ApiError ? error.message : "Something went wrong. Please try again."}
        </Alert>
      ) : null}
      <div>
        <Button onClick={onGenerate} disabled={triggering}>
          {triggering ? "Starting…" : "Generate Investment Committee Report"}
        </Button>
      </div>
    </div>
  );
}

function GeneratingPanel({
  snapshot,
  elapsedMs,
}: {
  snapshot: CommitteeProgressSnapshot | null;
  elapsedMs: number;
}) {
  const doneCount = snapshot?.specialists.filter((s) => s.finding !== null).length ?? 0;
  const nextIndex = snapshot?.specialists.findIndex((s) => s.finding === null) ?? -1;
  const elapsedSeconds = Math.round(elapsedMs / 1000);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">
          {doneCount} of {SPECIALISTS.length} specialists complete
        </span>
        <span className="text-muted-foreground">
          {elapsedSeconds > 0 ? `${elapsedSeconds}s elapsed` : "Starting…"}
        </span>
      </div>
      <div className="divide-y divide-border rounded-lg border border-border px-3">
        {SPECIALISTS.map((meta, i) => {
          const status = snapshot?.specialists.find((s) => s.path === meta.path);
          return (
            <SpecialistStatusRow
              key={meta.path}
              meta={meta}
              done={status?.finding !== null && status !== undefined}
              active={i === nextIndex}
            />
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        Once every specialist has finished, the Committee Chair synthesizes their findings and
        Compliance reviews the result -- this page updates automatically.
      </p>
    </div>
  );
}

function ReadyPanel({
  symbol,
  snapshot,
}: {
  symbol: string;
  snapshot: CommitteeProgressSnapshot;
}) {
  const report = snapshot.report;
  if (!report) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <CheckCircle2 size={16} className="text-success" />
        <span className="text-sm font-medium">Committee report ready</span>
        <ComplianceBadge approved={report.compliance.approved} />
      </div>
      <p className="line-clamp-3 text-sm text-muted-foreground">{report.result_json.summary}</p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ConfidenceMeter value={report.confidence_score} />
        <span className="text-xs text-muted-foreground">
          {report.result_json.source_findings.length} of {SPECIALISTS.length} specialists
          contributed
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link
          href={`/companies/${symbol}/report`}
          className="text-sm font-medium text-primary hover:underline"
        >
          Read the full report →
        </Link>
        <span className="text-muted-foreground">·</span>
        <Link
          href={`/companies/${symbol}/specialists`}
          className="text-sm font-medium text-primary hover:underline"
        >
          View specialist findings →
        </Link>
        <span className="text-muted-foreground">·</span>
        <Link
          href={`/companies/${symbol}/evidence`}
          className="text-sm font-medium text-primary hover:underline"
        >
          See evidence & citations →
        </Link>
      </div>
    </div>
  );
}
