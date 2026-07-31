import Link from "next/link";

import { cn } from "@/lib/utils";
import type { CitationLookupEntry } from "@/lib/api/types";

interface CitationRefsProps {
  refs: number[];
  lookup: Map<number, CitationLookupEntry>;
  /** When set, each chip links to `${linkHref}#citation-<n>` (used on
   * pages that share the Evidence page's citation list). Omitted for
   * specialist-local citations, which have no dedicated deep-link target. */
  linkHref?: string;
  className?: string;
}

export function CitationRefs({ refs, lookup, linkHref, className }: CitationRefsProps) {
  if (refs.length === 0) return null;

  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {refs.map((n) => {
        const entry = lookup.get(n);
        const chipClass =
          "inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-secondary px-1 text-[11px] font-medium text-secondary-foreground hover:bg-accent hover:text-accent-foreground hover:border-accent transition-colors";
        const title = entry ? `${entry.title} (${entry.sourceType})` : `Reference ${n}`;
        const ariaLabel = `Citation ${n}: ${title}`;

        if (linkHref) {
          return (
            <Link
              key={n}
              href={`${linkHref}#citation-${n}`}
              title={title}
              aria-label={ariaLabel}
              className={chipClass}
            >
              {n}
            </Link>
          );
        }
        return (
          <span key={n} title={title} aria-label={ariaLabel} className={chipClass}>
            {n}
          </span>
        );
      })}
    </span>
  );
}
