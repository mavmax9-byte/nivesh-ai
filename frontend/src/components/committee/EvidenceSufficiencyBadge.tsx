import { Badge } from "@/components/ui/badge";
import type { EvidenceSufficiency } from "@/lib/api/types";

const CONFIG: Record<EvidenceSufficiency, { label: string; variant: "success" | "warning" | "destructive" }> = {
  sufficient: { label: "Sufficient evidence", variant: "success" },
  partial: { label: "Partial evidence", variant: "warning" },
  insufficient: { label: "Insufficient evidence", variant: "destructive" },
};

export function EvidenceSufficiencyBadge({ value }: { value: EvidenceSufficiency }) {
  const config = CONFIG[value];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
