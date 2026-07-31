"use client";

import { use } from "react";
import Link from "next/link";
import { ChevronLeft, FileQuestion } from "lucide-react";

import { CompanySubNav } from "@/components/companies/CompanySubNav";
import { ConfidenceMeter } from "@/components/committee/ConfidenceMeter";
import { EvidenceSufficiencyBadge } from "@/components/committee/EvidenceSufficiencyBadge";
import { FindingRow } from "@/components/committee/FindingRow";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { getSpecialistFinding } from "@/lib/api/reports";
import {
  citationLookupFromSpecialist,
  domainNarrative,
  specialistAssessments,
  specialistMeta,
} from "@/lib/api/types";
import type { SpecialistFinding, SpecialistMeta } from "@/lib/api/types";

export default function SpecialistDetailPage({
  params,
}: {
  params: Promise<{ symbol: string; agent: string }>;
}) {
  const { symbol: rawSymbol, agent } = use(params);
  const symbol = rawSymbol.toUpperCase();
  const meta = specialistMeta(agent);

  const { data: finding, loading, error, notFound, refetch } = useAsync(
    () => (meta ? getSpecialistFinding(meta.path, symbol) : Promise.reject(new Error("unknown agent"))),
    [symbol, agent],
  );

  if (!meta) {
    return (
      <EmptyState
        icon={FileQuestion}
        title="Unknown specialist"
        description={`"${agent}" is not one of the five committee specialists.`}
        action={
          <Link
            href={`/companies/${symbol}/specialists`}
            className="text-sm font-medium text-primary hover:underline"
          >
            ← Back to specialists
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Company" title={symbol} />
      <CompanySubNav symbol={symbol} active={`/companies/${symbol}/specialists`} />

      <Link
        href={`/companies/${symbol}/specialists`}
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft size={15} />
        All specialists
      </Link>

      {loading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-28 rounded-lg" />
          <Skeleton className="h-56 rounded-lg" />
        </div>
      ) : notFound ? (
        <EmptyState
          title={`${meta.label} hasn't run yet`}
          description={`No finding has been generated for ${symbol} by this specialist.`}
          action={
            <Link href={`/companies/${symbol}`} className="text-sm font-medium text-primary hover:underline">
              ← Generate a committee report
            </Link>
          }
        />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : finding ? (
        <SpecialistDetail meta={meta} finding={finding} />
      ) : null}
    </div>
  );
}

function SpecialistDetail({
  meta,
  finding,
}: {
  meta: SpecialistMeta | undefined;
  finding: SpecialistFinding;
}) {
  if (!meta) return null;
  const result = finding.result_json;
  const assessments = specialistAssessments(result);
  const lookup = citationLookupFromSpecialist(result.citations);
  const narrative = domainNarrative(result, meta);
  const generatedAt = new Date(result.generated_at).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle className="text-xl">{meta.label}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {meta.description} · Generated {generatedAt}
            </p>
          </div>
          <EvidenceSufficiencyBadge value={result.evidence_sufficiency} />
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-base leading-relaxed">{result.summary}</p>
          <ConfidenceMeter value={result.confidence_score} />
        </CardContent>
      </Card>

      {narrative ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Assessment</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-muted-foreground">{narrative}</p>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Individual findings</CardTitle>
        </CardHeader>
        <CardContent>
          {assessments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No individual claims were surfaced.</p>
          ) : (
            <div className="flex flex-col">
              {assessments.map((a, i) => (
                <FindingRow
                  key={i}
                  metric={a.metric}
                  observation={a.observation}
                  stance={a.stance}
                  citationRefs={a.citation_refs}
                  lookup={lookup}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {result.caveats.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Caveats</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
              {result.caveats.map((c, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" />
                  {c}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {result.citations.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Citations</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col divide-y divide-border">
            {result.citations.map((c) => (
              <div key={c.index} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-border text-[11px] font-medium">
                    {c.index}
                  </span>
                  <span>{c.title}</span>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {c.source_type.replace(/_/g, " ")}
                  {c.evidence_date ? ` · ${c.evidence_date}` : ""}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Model: {finding.model_used} · Prompt version: {finding.prompt_version}
      </p>
    </div>
  );
}
