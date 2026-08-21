"use client";

import { PanelLeft, PanelTop } from "lucide-react";
import { useI18n } from "@/components/providers/locale-provider";
import type { LayoutStyle } from "@/lib/branding";

export function LayoutToggle({
  layout,
  onChange,
}: {
  layout: LayoutStyle;
  onChange: (layout: LayoutStyle) => void;
}) {
  const { t } = useI18n();
  const nextLayout = layout === "sidebar" ? "topbar" : "sidebar";
  const label = t(layout === "sidebar" ? "layout.style.switchToTopbar" : "layout.style.switchToSidebar");
  const Icon = nextLayout === "topbar" ? PanelTop : PanelLeft;

  return (
    <button
      type="button"
      onClick={() => onChange(nextLayout)}
      title={label}
      aria-label={label}
      className="control-glow grid h-9 w-9 place-items-center rounded-lg border border-border/80 bg-muted/45 text-muted-foreground shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

export function LayoutControl({
  value,
  onChange,
}: {
  value: LayoutStyle;
  onChange: (value: LayoutStyle) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="grid grid-cols-2 gap-1 rounded-lg border border-border/80 bg-muted/45 p-1 shadow-sm" aria-label={t("layout.style.label")}>
      <button
        type="button"
        onClick={() => onChange("sidebar")}
        title={t("layout.style.sidebar")}
        aria-pressed={value === "sidebar"}
        className={`inline-flex min-h-8 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors ${value === "sidebar" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"}`}
      >
        <PanelLeft className="h-3.5 w-3.5" />
        <span>{t("layout.style.sidebar")}</span>
      </button>
      <button
        type="button"
        onClick={() => onChange("topbar")}
        title={t("layout.style.topbar")}
        aria-pressed={value === "topbar"}
        className={`inline-flex min-h-8 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors ${value === "topbar" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"}`}
      >
        <PanelTop className="h-3.5 w-3.5" />
        <span>{t("layout.style.topbar")}</span>
      </button>
    </div>
  );
}
