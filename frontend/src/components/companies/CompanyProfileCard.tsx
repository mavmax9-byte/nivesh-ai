import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Company, ResearchDossier } from "@/lib/api/types";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" });
}

function formatPrice(value: string | null): string {
  if (value === null) return "—";
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return "—";
  return `₹${parsed.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function CompanyProfileCard({
  company,
  dossier,
}: {
  company: Company;
  dossier: ResearchDossier | null;
}) {
  const snapshot = dossier?.latest_version?.snapshot ?? null;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="text-xl">{company.name}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {company.symbol} · {company.exchange.name}
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold tabular-nums">{formatPrice(snapshot?.latest_price ?? null)}</p>
          <p className="text-xs text-muted-foreground">
            as of {formatDate(snapshot?.latest_trade_date ?? null)}
          </p>
        </div>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2">
        {company.sector ? (
          <span className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground">
            {company.sector}
          </span>
        ) : null}
        {company.industry ? (
          <span className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground">
            {company.industry}
          </span>
        ) : null}
        {!dossier ? (
          <span className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted-foreground">
            No research dossier synced yet
          </span>
        ) : null}
      </CardContent>
    </Card>
  );
}
