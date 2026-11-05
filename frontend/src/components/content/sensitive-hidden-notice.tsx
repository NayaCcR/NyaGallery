"use client";

import { useEffect, useState } from "react";
import { EyeOff } from "lucide-react";
import { useContentPreferences } from "@/components/providers/content-preferences-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { NyaApi } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Explains that R-18 assets are hidden by the content filter and offers a one-click way to show them.
 * Renders nothing for guests, when sensitive content is already shown, or when nothing is hidden.
 */
export function SensitiveHiddenNotice({ className }: { className?: string }) {
  const { t } = useI18n();
  const { ready, canViewSensitiveContent, showSensitive, setShowSensitive } = useContentPreferences();
  const [count, setCount] = useState<number | null>(null);
  const active = ready && canViewSensitiveContent && !showSensitive;

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    NyaApi.sensitiveAssetCount()
      .then((result) => {
        if (!cancelled) setCount(result.count);
      })
      .catch(() => {
        if (!cancelled) setCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  if (!active || !count) return null;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-foreground",
        className
      )}
      role="status"
    >
      <EyeOff className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
      <span>{t("content.sensitiveHidden", { count })}</span>
      <Button type="button" size="sm" variant="outline" className="ml-auto h-7 px-2.5 text-xs" onClick={() => setShowSensitive(true)}>
        {t("content.showSensitiveNow")}
      </Button>
    </div>
  );
}
