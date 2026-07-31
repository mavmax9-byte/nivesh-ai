import { CitationRefs } from "@/components/committee/CitationRefs";
import { StanceBadge } from "@/components/committee/StanceBadge";
import { formatMetricLabel } from "@/lib/api/types";
import type { CitationLookupEntry, Stance } from "@/lib/api/types";

interface FindingRowProps {
  metric: string;
  observation: string;
  stance: Stance;
  citationRefs: number[];
  lookup: Map<number, CitationLookupEntry>;
  linkHref?: string;
}

export function FindingRow({
  metric,
  observation,
  stance,
  citationRefs,
  lookup,
  linkHref,
}: FindingRowProps) {
  return (
    <div className="flex flex-col gap-1.5 border-b border-border py-3 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">{formatMetricLabel(metric)}</span>
        <StanceBadge stance={stance} />
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">{observation}</p>
      <CitationRefs refs={citationRefs} lookup={lookup} linkHref={linkHref} />
    </div>
  );
}
