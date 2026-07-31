import Link from "next/link";
import { Search, ShieldCheck } from "lucide-react";

export function Navbar() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border px-6">
      <Link href="/" className="flex items-center gap-2 font-semibold">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary text-xs text-primary-foreground">
          N
        </span>
        Nivesh AI
      </Link>
      <div className="flex items-center gap-4">
        <Link
          href="/companies"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <Search size={14} />
          Search companies
        </Link>
        <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
          <ShieldCheck size={13} />
          Research only -- not investment advice
        </span>
      </div>
    </header>
  );
}
