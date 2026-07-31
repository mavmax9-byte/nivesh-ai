import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Stance } from "@/lib/api/types";

const STANCE_CONFIG: Record<Stance, { label: string; variant: "success" | "destructive" | "default"; icon: typeof TrendingUp }> = {
  positive: { label: "Positive", variant: "success", icon: TrendingUp },
  negative: { label: "Negative", variant: "destructive", icon: TrendingDown },
  neutral: { label: "Neutral", variant: "default", icon: Minus },
};

export function StanceBadge({ stance }: { stance: Stance }) {
  const config = STANCE_CONFIG[stance];
  const Icon = config.icon;
  return (
    <Badge variant={config.variant}>
      <Icon size={11} />
      {config.label}
    </Badge>
  );
}
