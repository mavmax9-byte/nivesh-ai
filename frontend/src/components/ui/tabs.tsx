"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";

export interface TabItem {
  href: string;
  label: string;
  count?: number;
}

export function LinkTabs({ items, activeHref }: { items: TabItem[]; activeHref: string }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-border" role="tablist">
      {items.map((item) => {
        const active = item.href === activeHref;
        return (
          <Link
            key={item.href}
            href={item.href}
            role="tab"
            aria-selected={active}
            className={cn(
              "relative flex shrink-0 items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors",
              active
                ? "text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
            {item.count !== undefined ? (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-xs",
                  active ? "bg-accent text-accent-foreground" : "bg-secondary text-muted-foreground",
                )}
              >
                {item.count}
              </span>
            ) : null}
            {active ? (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-primary" />
            ) : null}
          </Link>
        );
      })}
    </div>
  );
}
