import { Split } from "lucide-react";

import { CitationRefs } from "@/components/committee/CitationRefs";
import { StanceBadge } from "@/components/committee/StanceBadge";
import { SPECIALISTS } from "@/lib/api/types";
import type { AgentDisagreement, CitationLookupEntry } from "@/lib/api/types";

function agentLabel(agentCode: string): string {
  const meta = SPECIALISTS.find((s) => s.agentCode === agentCode);
  return meta?.shortLabel ?? agentCode.replace(/_/g, " ");
}

export function DisagreementCard({
  disagreement,
  lookup,
  linkHref,
}: {
  disagreement: AgentDisagreement;
  lookup: Map<number, CitationLookupEntry>;
  linkHref?: string;
}) {
  return (
    <div className="rounded-lg border border-warning/30 bg-warning-bg/40 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Split size={15} className="text-warning" />
        <span className="text-sm font-semibold text-warning">{disagreement.topic}</span>
      </div>
      <div className="flex flex-col gap-3">
        {disagreement.positions.map((position, i) => (
          <div key={`${position.agent_code}-${i}`} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{agentLabel(position.agent_code)}</span>
              <StanceBadge stance={position.stance} />
            </div>
            <p className="text-sm text-muted-foreground">{position.summary}</p>
            <CitationRefs refs={position.citation_refs} lookup={lookup} linkHref={linkHref} />
          </div>
        ))}
      </div>
    </div>
  );
}
