"use client";

import { use } from "react";
import Link from "next/link";
import { Clock } from "lucide-react";

import { CompanySubNav } from "@/components/companies/CompanySubNav";
import { SpecialistSummaryCard } from "@/components/committee/SpecialistSummaryCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { pollSpecialistFinding } from "@/lib/api/reports";
import { SPECIALISTS } from "@/lib/api/types";

export default function SpecialistsPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: rawSymbol } = use(params);
  const symbol = rawSymbol.toUpperCase();

  const { data, loading, error, refetch } = useAsync(
    () => Promise.all(SPECIALISTS.map((s) => pollSpecialistFinding(s.path, symbol))),
    [symbol],
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Company" title={symbol} />
      <CompanySubNav symbol={symbol} active={`/companies/${symbol}/specialists`} />

      <div>
        <h2 className="text-lg font-semibold">Specialist findings</h2>
        <p className="text-sm text-muted-foreground">
          Each specialist reasons independently over its own slice of the shared evidence pool.
          Every claim below cites a real, resolvable source.
        </p>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SPECIALISTS.map((s) => (
            <Skeleton key={s.path} className="h-40 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SPECIALISTS.map((meta, i) => {
            const finding = data?.[i] ?? null;
            if (!finding) {
              return (
                <Card key={meta.path} className="flex h-full flex-col justify-between gap-3 opacity-70">
                  <div>
                    <p className="font-semibold">{meta.label}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{meta.description}</p>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Clock size={13} />
                    Not generated yet
                  </div>
                </Card>
              );
            }
            return (
              <SpecialistSummaryCard
                key={meta.path}
                meta={meta}
                finding={finding}
                href={`/companies/${symbol}/specialists/${meta.path}`}
              />
            );
          })}
        </div>
      )}

      {!loading && !error && data?.every((f) => f === null) ? (
        <p className="text-sm text-muted-foreground">
          No specialist has run yet for this company.{" "}
          <Link href={`/companies/${symbol}`} className="font-medium text-primary hover:underline">
            Generate an Investment Committee report
          </Link>{" "}
          to run all five at once.
        </p>
      ) : null}
    </div>
  );
}
