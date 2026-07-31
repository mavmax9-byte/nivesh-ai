import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceMeter } from "@/components/committee/ConfidenceMeter";
import { EvidenceSufficiencyBadge } from "@/components/committee/EvidenceSufficiencyBadge";
import type { SpecialistFinding, SpecialistMeta } from "@/lib/api/types";

export function SpecialistSummaryCard({
  meta,
  finding,
  href,
}: {
  meta: SpecialistMeta;
  finding: SpecialistFinding;
  href: string;
}) {
  return (
    <Link href={href} className="group block">
      <Card className="h-full transition-shadow hover:shadow-md group-hover:border-primary/40">
        <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
          <div>
            <CardTitle className="text-base">{meta.label}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{meta.description}</p>
          </div>
          <ChevronRight
            size={18}
            className="mt-1 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          />
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="line-clamp-2 text-sm text-muted-foreground">{finding.result_json.summary}</p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <EvidenceSufficiencyBadge value={finding.evidence_sufficiency} />
            <ConfidenceMeter value={finding.confidence_score} size="sm" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
