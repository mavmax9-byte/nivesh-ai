import { CheckCircle2, CircleDashed } from "lucide-react";

import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { SpecialistMeta } from "@/lib/api/types";

export function SpecialistStatusRow({
  meta,
  done,
  active,
}: {
  meta: SpecialistMeta;
  done: boolean;
  /** true while this row is still the "current" one being worked on --
   * purely a visual hint, since specialists actually run sequentially on
   * the backend but the frontend can't observe per-specialist start
   * times, only completion. */
  active: boolean;
}) {
  return (
    <div className="flex items-center gap-3 py-2">
      {done ? (
        <CheckCircle2 size={18} className="shrink-0 text-success" />
      ) : active ? (
        <Spinner size={18} className="shrink-0 text-primary" />
      ) : (
        <CircleDashed size={18} className="shrink-0 text-muted-foreground/40" />
      )}
      <div className="flex flex-1 flex-col">
        <span className={cn("text-sm font-medium", !done && !active && "text-muted-foreground")}>
          {meta.label}
        </span>
        <span className="text-xs text-muted-foreground">{meta.description}</span>
      </div>
      <span
        className={cn(
          "text-xs font-medium",
          done ? "text-success" : active ? "text-primary" : "text-muted-foreground/60",
        )}
      >
        {done ? "Complete" : active ? "Analyzing…" : "Queued"}
      </span>
    </div>
  );
}
