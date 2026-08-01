import { ConfidenceMeter } from "@/components/committee/ConfidenceMeter";
import { EvidenceSufficiencyBadge } from "@/components/committee/EvidenceSufficiencyBadge";
import { Card } from "@/components/ui/card";
import type { PlannedHolding } from "@/lib/api/types";

function formatCurrency(value: number): string {
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function HoldingCard({ holding }: { holding: PlannedHolding }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{holding.symbol}</p>
          <p className="text-xs text-muted-foreground">
            {holding.company_name}
            {holding.sector ? ` · ${holding.sector}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="font-semibold tabular-nums">{formatCurrency(holding.allocated_amount)}</p>
          <p className="text-xs text-muted-foreground tabular-nums">
            {Math.round(holding.allocated_weight * 100)}%
          </p>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">{holding.thesis}</p>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <ConfidenceMeter value={holding.confidence_score} size="sm" />
        <EvidenceSufficiencyBadge value={holding.evidence_sufficiency} />
      </div>

      <p className="text-xs text-muted-foreground">{holding.weight_rationale}</p>

      {holding.top_citation_title ? (
        <p className="border-t border-border pt-2 text-xs text-muted-foreground">
          Cited: {holding.top_citation_title}
        </p>
      ) : null}
    </Card>
  );
}
