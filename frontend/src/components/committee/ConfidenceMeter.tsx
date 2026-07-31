import { cn } from "@/lib/utils";

function tone(pct: number) {
  if (pct >= 65) return { bar: "bg-success", text: "text-success" };
  if (pct >= 35) return { bar: "bg-warning", text: "text-warning" };
  return { bar: "bg-destructive", text: "text-destructive" };
}

export function ConfidenceMeter({
  value,
  size = "default",
  className,
}: {
  value: number;
  size?: "default" | "sm";
  className?: string;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const { bar, text } = tone(pct);

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Confidence"
        className={cn("overflow-hidden rounded-full bg-muted", size === "sm" ? "h-1.5 w-16" : "h-2 w-28")}
      >
        <div
          className={cn("h-full rounded-full transition-all duration-500", bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={cn("font-semibold tabular-nums", text, size === "sm" ? "text-xs" : "text-sm")}>
        {pct}%
      </span>
    </div>
  );
}
