"use client";

import { useMemo, useState } from "react";
import { SearchX } from "lucide-react";

import { CompanyCard } from "@/components/companies/CompanyCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAsync } from "@/hooks/useAsync";
import { listCompanies } from "@/lib/api/companies";

export default function CompaniesPage() {
  const [query, setQuery] = useState("");
  const { data: companies, loading, error, refetch } = useAsync(() => listCompanies(200), []);

  const filtered = useMemo(() => {
    if (!companies) return [];
    const q = query.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter(
      (c) =>
        c.symbol.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q) ||
        c.sector?.toLowerCase().includes(q) ||
        c.industry?.toLowerCase().includes(q),
    );
  }, [companies, query]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Company search"
        description="Search the companies already tracked by the Nivesh AI research index."
      />

      <Input
        placeholder="Search by symbol, name, sector, or industry…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="max-w-md"
        aria-label="Search companies"
      />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title={companies && companies.length > 0 ? "No matches" : "No companies yet"}
          description={
            companies && companies.length > 0
              ? `No company matches "${query}". Try a different symbol, name, sector, or industry.`
              : "No companies have been synced into the research index yet."
          }
        />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {filtered.length} compan{filtered.length === 1 ? "y" : "ies"}
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
