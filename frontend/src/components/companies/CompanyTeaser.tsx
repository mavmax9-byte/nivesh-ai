"use client";

import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { listCompanies } from "@/lib/api/companies";

export function CompanyTeaser() {
  const { data, loading, error } = useAsync(() => listCompanies(8), []);

  if (loading) {
    return (
      <div className="flex flex-wrap justify-center gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-24 rounded-full" />
        ))}
      </div>
    );
  }

  if (error || !data || data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No companies tracked yet -- sync one from the backend to get started.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap justify-center gap-2">
      {data.map((company) => (
        <Link
          key={company.id}
          href={`/companies/${company.symbol}`}
          className="rounded-full border border-border bg-card px-3.5 py-1.5 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-accent hover:text-accent-foreground"
        >
          {company.symbol}
        </Link>
      ))}
    </div>
  );
}
