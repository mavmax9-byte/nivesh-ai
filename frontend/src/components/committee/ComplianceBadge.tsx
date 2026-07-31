import { ShieldCheck, ShieldX } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export function ComplianceBadge({ approved }: { approved: boolean }) {
  return approved ? (
    <Badge variant="success">
      <ShieldCheck size={11} />
      Compliance approved
    </Badge>
  ) : (
    <Badge variant="destructive">
      <ShieldX size={11} />
      Compliance rejected
    </Badge>
  );
}
