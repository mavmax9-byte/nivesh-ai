"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, Eye, Home, PieChart, Wallet } from "lucide-react";

import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/planner", label: "Planner", icon: PieChart },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/watchlist", label: "Watchlist", icon: Eye },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-56 shrink-0 border-r border-border p-4 md:block">
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent font-medium text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
