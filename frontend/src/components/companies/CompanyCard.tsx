import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { Company } from "@/lib/api/types";

export function CompanyCard({ company }: { company: Company }) {
  return (
    <Link href={`/companies/${company.symbol}`} className="group block">
      <Card className="flex h-full flex-col justify-between gap-3 transition-shadow hover:shadow-md group-hover:border-primary/40">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold">{company.symbol}</p>
            <p className="line-clamp-1 text-sm text-muted-foreground">{company.name}</p>
          </div>
          <ArrowRight
            size={16}
            className="mt-1 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span className="rounded border border-border px-1.5 py-0.5">{company.exchange.code}</span>
          {company.sector ? (
            <span className="rounded border border-border px-1.5 py-0.5">{company.sector}</span>
          ) : null}
        </div>
      </Card>
    </Link>
  );
}
