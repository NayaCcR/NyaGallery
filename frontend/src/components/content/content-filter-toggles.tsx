"use client";

import { useContentPreferences } from "@/components/providers/content-preferences-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";

export function ContentFilterToggles({ className }: { className?: string }) {
  const { t } = useI18n();
  const { showSensitive, setShowSensitive, showAi, setShowAi, canViewSensitiveContent } =
    useContentPreferences();

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {canViewSensitiveContent && (
        <FilterSwitch
          label="R-18"
          checked={showSensitive}
          onCheckedChange={setShowSensitive}
          title={t("content.showSensitive")}
        />
      )}
      <FilterSwitch
        label="AI"
        checked={showAi}
        onCheckedChange={setShowAi}
        title={t("content.showAi")}
      />
    </div>
  );
}

function FilterSwitch({
  label,
  checked,
  onCheckedChange,
  title,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  title: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={title}
      title={title}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "inline-flex h-8 select-none items-center gap-2 rounded-full border px-3 text-xs font-medium transition-colors focus-ring",
        checked
          ? "border-primary/50 bg-primary/10 text-foreground"
          : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
      )}
    >
      <span>{label}</span>
      <span
        className={cn(
          "relative inline-flex h-4 w-7 items-center rounded-full transition-colors",
          checked ? "bg-primary" : "bg-muted-foreground/30"
        )}
      >
        <span
          className={cn(
            "inline-block h-3 w-3 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-3.5" : "translate-x-0.5"
          )}
        />
      </span>
    </button>
  );
}