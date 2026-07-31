import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Info, XCircle } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const alertVariants = cva("flex items-start gap-3 rounded-lg border p-4 text-sm", {
  variants: {
    variant: {
      info: "border-border bg-secondary text-secondary-foreground",
      warning: "border-warning/30 bg-warning-bg text-warning",
      destructive: "border-destructive/30 bg-destructive-bg text-destructive",
    },
  },
  defaultVariants: {
    variant: "info",
  },
});

const ICONS = {
  info: Info,
  warning: AlertTriangle,
  destructive: XCircle,
} as const;

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  title?: string;
}

export function Alert({ className, variant = "info", title, children, ...props }: AlertProps) {
  const Icon = ICONS[variant ?? "info"];
  return (
    <div className={cn(alertVariants({ variant }), className)} {...props}>
      <Icon size={18} className="mt-0.5 shrink-0" />
      <div className="flex flex-col gap-1">
        {title ? <p className="font-medium">{title}</p> : null}
        <div className="text-current/90 leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
