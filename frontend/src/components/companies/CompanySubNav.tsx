import { LinkTabs } from "@/components/ui/tabs";

export function CompanySubNav({ symbol, active }: { symbol: string; active: string }) {
  const base = `/companies/${symbol}`;
  return (
    <LinkTabs
      activeHref={active}
      items={[
        { href: base, label: "Overview" },
        { href: `${base}/report`, label: "Research Report" },
        { href: `${base}/specialists`, label: "Specialist Findings" },
        { href: `${base}/evidence`, label: "Evidence & Citations" },
      ]}
    />
  );
}
