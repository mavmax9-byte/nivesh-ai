"use client";

import { use, useMemo } from "react";
import Link from "next/link";
import { BookOpen, Landmark, Newspaper, ScrollText, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CompanySubNav } from "@/components/companies/CompanySubNav";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { getCommitteeReport } from "@/lib/api/reports";
import { SPECIALISTS } from "@/lib/api/types";
import type { CommitteeCitationRef } from "@/lib/api/types";

const SOURCE_TYPE_LABELS: Record<string, string> = {
  financial_statement: "Financial statements",
  corporate_filing: "Corporate filings",
  document_section: "Filing document sections",
  technical_indicator: "Technical indicators",
  news_article: "News articles",
  research_summary: "Research summaries",
  company_profile: "Company profile",
  computed_ratio: "Computed ratios",
};

const SOURCE_TYPE_ICONS: Record<string, LucideIcon> = {
  financial_statement: Landmark,
  corporate_filing: ScrollText,
  document_section: ScrollText,
  technical_indicator: TrendingUp,
  news_article: Newspaper,
  research_summary: BookOpen,
  company_profile: BookOpen,
  computed_ratio: TrendingUp,
};

function agentLabel(agentCode: string): string {
  return SPECIALISTS.find((s) => s.agentCode === agentCode)?.shortLabel ?? agentCode;
}

export default function EvidencePage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: rawSymbol } = use(params);
  const symbol = rawSymbol.toUpperCase();

  const { data: report, loading, error, notFound, refetch } = useAsync(
    () => getCommitteeReport(symbol),
    [symbol],
  );

  const grouped = useMemo(() => {
    if (!report) return [];
    const groups = new Map<string, CommitteeCitationRef[]>();
    for (const citation of report.result_json.citations) {
      const list = groups.get(citation.source_type) ?? [];
      list.push(citation);
      groups.set(citation.source_type, list);
    }
    return Array.from(groups.entries()).sort((a, b) => b[1].length - a[1].length);
  }, [report]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Company" title={symbol} />
      <CompanySubNav symbol={symbol} active={`/companies/${symbol}/evidence`} />

      <div>
        <h2 className="text-lg font-semibold">Evidence &amp; citations</h2>
        <p className="text-sm text-muted-foreground">
          Every citation the committee&apos;s synthesized report relies on, deduplicated across
          all five specialists and grouped by evidence type.
        </p>
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
        </div>
      ) : notFound ? (
        <EmptyState
          title="No evidence to show yet"
          description="Citations appear here once a committee report has been generated for this company."
          action={
            <Link href={`/companies/${symbol}`} className="text-sm font-medium text-primary hover:underline">
              ← Go generate one
            </Link>
          }
        />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : report ? (
        <>
          <p className="text-sm text-muted-foreground">
            {report.result_json.citations.length} unique source
            {report.result_json.citations.length === 1 ? "" : "s"} across{" "}
            {grouped.length} evidence type{grouped.length === 1 ? "" : "s"}
          </p>
          <div className="flex flex-col gap-6">
            {grouped.map(([sourceType, citations]) => {
              const Icon = SOURCE_TYPE_ICONS[sourceType] ?? BookOpen;
              return (
                <Card key={sourceType}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Icon size={16} className="text-muted-foreground" />
                      {SOURCE_TYPE_LABELS[sourceType] ?? sourceType.replace(/_/g, " ")}
                      <span className="ml-auto text-sm font-normal text-muted-foreground">
                        {citations.length}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col divide-y divide-border">
                    {citations
                      .sort((a, b) => a.global_index - b.global_index)
                      .map((citation) => (
                        <div
                          key={citation.global_index}
                          id={`citation-${citation.global_index}`}
                          className="flex flex-wrap items-start justify-between gap-3 py-3 scroll-mt-24"
                        >
                          <div className="flex items-start gap-2">
                            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border border-border text-[11px] font-medium">
                              {citation.global_index}
                            </span>
                            <div>
                              <p className="text-sm font-medium">{citation.title}</p>
                              <p className="text-xs text-muted-foreground">
                                {citation.evidence_date ?? "Undated"}
                              </p>
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {citation.source_agent_codes.map((code) => (
                              <span
                                key={code}
                                className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-secondary-foreground"
                              >
                                {agentLabel(code)}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      ) : null}
    </div>
  );
}
