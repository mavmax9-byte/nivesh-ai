import Link from "next/link";
import {
  BookOpenCheck,
  Landmark,
  LineChart,
  Newspaper,
  ScrollText,
  Search,
  ShieldCheck,
  TriangleAlert,
  Users,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CompanyTeaser } from "@/components/companies/CompanyTeaser";
import { cn } from "@/lib/utils";

const SPECIALIST_ICONS = [
  { icon: Landmark, label: "Fundamental", detail: "Financial statements & profitability" },
  { icon: LineChart, label: "Technical", detail: "Trend, momentum & volatility" },
  { icon: ScrollText, label: "Valuation", detail: "P/E and valuation context" },
  { icon: Newspaper, label: "News & Sentiment", detail: "Recent coverage & disclosures" },
  { icon: TriangleAlert, label: "Risk", detail: "Leverage & disclosed risk factors" },
];

const STEPS = [
  {
    title: "Search a company",
    detail: "Look up any NSE/BSE company already tracked by the research index.",
  },
  {
    title: "Five specialists analyze in parallel",
    detail: "Each reasons only over evidence retrieved from filings, statements, and market data.",
  },
  {
    title: "The Committee Chair synthesizes",
    detail: "Findings are cross-checked, disagreements are surfaced, never resolved into a false consensus.",
  },
  {
    title: "Compliance gates the result",
    detail: "A deterministic check blocks anything resembling investment advice before it's ever shown.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-col gap-20 pb-16">
      {/* Hero */}
      <section className="flex flex-col items-center gap-6 pt-8 text-center">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-3 py-1 text-xs font-medium text-secondary-foreground">
          <Users size={13} />
          Multi-agent AI Investment Committee
        </span>
        <h1 className="max-w-3xl text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
          Evidence-backed equity research, synthesized by a committee of AI specialists
        </h1>
        <p className="max-w-xl text-balance text-base text-muted-foreground sm:text-lg">
          Nivesh AI runs five specialist agents over real filings, financials, and market data for
          Indian equities, then synthesizes their findings into one cited, cross-checked report --
          every claim traces back to real evidence.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link href="/companies" className={cn(buttonVariants({ size: "lg" }))}>
            <Search size={16} className="mr-1.5" />
            Search a company
          </Link>
        </div>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ShieldCheck size={13} />
          Research only -- Nivesh AI never places, recommends, or executes trades.
        </p>
      </section>

      {/* Specialist roster */}
      <section className="flex flex-col gap-6">
        <div className="text-center">
          <h2 className="text-lg font-semibold">The committee</h2>
          <p className="text-sm text-muted-foreground">
            Five specialists, one shared pool of evidence, zero unsupported claims.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {SPECIALIST_ICONS.map(({ icon: Icon, label, detail }) => (
            <Card key={label} className="flex flex-col items-center gap-2 p-4 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
                <Icon size={18} />
              </div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-xs text-muted-foreground">{detail}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="flex flex-col gap-6">
        <div className="text-center">
          <h2 className="text-lg font-semibold">How a report gets built</h2>
          <p className="text-sm text-muted-foreground">
            Every step is deterministic where it can be, and cited where it isn&apos;t.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, i) => (
            <Card key={step.title} className="flex flex-col gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                {i + 1}
              </span>
              <p className="font-medium">{step.title}</p>
              <p className="text-sm text-muted-foreground">{step.detail}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* Live teaser */}
      <section className="flex flex-col items-center gap-4">
        <div className="flex items-center gap-2 text-center">
          <BookOpenCheck size={16} className="text-muted-foreground" />
          <h2 className="text-sm font-medium text-muted-foreground">
            Already in the research index
          </h2>
        </div>
        <CompanyTeaser />
        <Link href="/companies" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
          Browse all companies →
        </Link>
      </section>
    </div>
  );
}
