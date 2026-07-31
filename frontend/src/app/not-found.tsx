import Link from "next/link";
import { Compass } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="Page not found"
      description="The page you're looking for doesn't exist."
      action={
        <Link href="/" className="text-sm font-medium text-primary hover:underline">
          ← Back to home
        </Link>
      }
    />
  );
}
