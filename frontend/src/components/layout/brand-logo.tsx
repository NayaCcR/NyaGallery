"use client";

import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { Branding, LayoutStyle } from "@/lib/branding";

/** Brand mark, falling back to a tinted tile so a missing logo never breaks the shell. */
export function BrandLogo({
  branding,
  variant,
  showWordmark = true,
  subtitle,
  className,
}: {
  branding: Branding;
  variant: LayoutStyle;
  showWordmark?: boolean;
  subtitle?: string;
  className?: string;
}) {
  return (
    <Link href="/" className={cn("flex min-w-0 items-center gap-3", className)}>
      <BrandMark branding={branding} size={branding.logoSize[variant]} />
      {showWordmark && (
        <span className="min-w-0">
          <span
            className={cn(
              "block truncate font-semibold tracking-wide text-primary",
              variant === "sidebar" ? "text-lg" : "text-sm"
            )}
          >
            {branding.appName}
          </span>
          {subtitle && <span className="block truncate text-[11px] uppercase text-muted-foreground">{subtitle}</span>}
        </span>
      )}
    </Link>
  );
}

export function BrandMark({ branding, size }: { branding: Branding; size: number }) {
  const [failed, setFailed] = useState(false);
  const dimension = { width: size, height: size };

  if (branding.logoUrl && !failed) {
    return (
      <img
        src={branding.logoUrl}
        alt={branding.appName}
        style={dimension}
        onError={() => setFailed(true)}
        className="shrink-0 rounded-md object-contain"
      />
    );
  }

  return (
    <span
      style={dimension}
      aria-label={branding.appName}
      className="grid shrink-0 place-items-center rounded-md bg-primary text-sm font-bold text-primary-foreground"
    >
      {branding.logoFallbackText}
    </span>
  );
}
