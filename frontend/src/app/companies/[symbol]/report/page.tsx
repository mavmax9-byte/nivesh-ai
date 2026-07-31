"use client";

import { use } from "react";
import Link from "next/link";
import { FileText, TriangleAlert } from "lucide-react";

import { CompanySubNav } from "@/components/companies/CompanySubNav";
import { ComplianceBadge } from "@/components/committee/ComplianceBadge";
import { ConfidenceMeter } from "@/components/committee/ConfidenceMeter";
import { DisagreementCard } from "@/components/committee/DisagreementCard";
import { EvidenceSufficiencyBadge } from "@/components/committee/EvidenceSufficiencyBadge";
import { FindingRow } from "@/components/committee/FindingRow";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { getCommitteeReport } from "@/lib/api/reports";
import { citationLookupFromCommittee, SPECIALISTS } from "@/lib/api/types";
import type { CommitteeReport } from "@/lib/api/types";

export default function ResearchReportPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol: rawSymbol } = use(params);
  const symbol = rawSymbol.toUpperCase();

  const { data: report, loading, error, notFound, refetch } = useAsync(
    () => getCommitteeReport(symbol),
    [symbol],
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Company" title={symbol} />
      <CompanySubNav symbol={symbol} active={`/companies/${symbol}/report`} />

      {loading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-32 rounded-lg" />
          <Skeleton className="h-64 rounded-lg" />
        </div>
      ) : notFound ? (
        <EmptyState
          icon={FileText}
          title="No research report yet"
          description="This company doesn't have a completed committee report. Generate one from the overview page."
          action={
            <Link href={`/companies/${symbol}`} className="text-sm font-medium text-primary hover:underline">
              ← Go generate one
            </Link>
          }
        />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : report ? (
        <ReportBody symbol={symbol} report={report} />
      ) : null}
    </div>
  );
}

function ReportBody({ symbol, report }: { symbol: string; report: CommitteeReport }) {
  const decision = report.result_json;
  const lookup = citationLookupFromCommittee(decision.citations);
  const evidenceHref = `/companies/${symbol}/evidence`;
  const generatedAt = new Date(decision.generated_at).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <div className="flex flex-col gap-6">
      {/* Header card */}
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle className="text-xl">Research Report -- {symbol}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Generated {generatedAt} · {decision.source_findings.length} of {SPECIALISTS.length}{" "}
              specialists contributed
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <ComplianceBadge approved={report.compliance.approved} />
            <EvidenceSufficiencyBadge value={decision.evidence_sufficiency} />
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-base leading-relaxed">{decision.summary}</p>
          <ConfidenceMeter value={report.confidence_score} />
        </CardContent>
      </Card>

      {decision.failed_specialists.length > 0 ? (
        <Alert variant="warning" title="Partial synthesis">
          {decision.failed_specialists
            .map((code) => SPECIALISTS.find((s) => s.agentCode === code)?.label ?? code)
            .join(", ")}{" "}
          did not complete for this run. The report above reflects only the specialists that
          succeeded.
        </Alert>
      ) : null}

      {/* Themed findings */}
      <Card>
        <CardHeader>
          <CardTitle>Findings</CardTitle>
        </CardHeader>
        <CardContent>
          {decision.findings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No individual findings were surfaced.</p>
          ) : (
            <div className="flex flex-col">
              {decision.findings.map((finding, i) => (
                <FindingRow
                  key={i}
                  metric={finding.theme}
                  observation={finding.observation}
                  stance={finding.stance}
                  citationRefs={finding.citation_refs}
                  lookup={lookup}
                  linkHref={evidenceHref}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Disagreements */}
      {decision.disagreements.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TriangleAlert size={17} className="text-warning" />
              Where specialists disagree
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              The committee never resolves disagreement into a single verdict -- both sides are
              shown as reported.
            </p>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {decision.disagreements.map((d, i) => (
              <DisagreementCard key={i} disagreement={d} lookup={lookup} linkHref={evidenceHref} />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {/* Caveats */}
      {decision.caveats.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Caveats</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
              {decision.caveats.map((c, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" />
                  {c}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {/* Source manifest */}
      <Card>
        <CardHeader>
          <CardTitle>Contributing specialists</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col divide-y divide-border">
          {decision.source_findings.map((sf) => {
            const meta = SPECIALISTS.find((s) => s.agentCode === sf.agent_code);
            return (
              <Link
                key={sf.agent_code}
                href={meta ? `/companies/${symbol}/specialists/${meta.path}` : "#"}
                className="flex items-center justify-between gap-3 py-3 text-sm hover:text-primary"
              >
                <span className="font-medium">{meta?.label ?? sf.agent_code}</span>
                <div className="flex items-center gap-3">
                  <EvidenceSufficiencyBadge value={sf.evidence_sufficiency} />
                  <ConfidenceMeter value={sf.confidence_score} size="sm" />
                </div>
              </Link>
            );
          })}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {decision.citations.length} citation{decision.citations.length === 1 ? "" : "s"} across
          this report
        </span>
        <Link href={evidenceHref} className="font-medium text-primary hover:underline">
          View all evidence & citations →
        </Link>
      </div>
    </div>
  );
}
