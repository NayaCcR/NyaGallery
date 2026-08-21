"use client";

import { Menu, X } from "lucide-react";
import { useI18n } from "@/components/providers/locale-provider";
import { LanguageSelect } from "@/components/layout/language-select";
import { LayoutToggle } from "@/components/layout/layout-control";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import type { LayoutStyle } from "@/lib/branding";

export function ShellActions({
  layout,
  switchable,
  onChangeLayout,
  mobile = false,
  mobileOpen = false,
  onToggleMobile,
}: {
  layout: LayoutStyle;
  switchable: boolean;
  onChangeLayout: (layout: LayoutStyle) => void;
  mobile?: boolean;
  mobileOpen?: boolean;
  onToggleMobile?: () => void;
}) {
  const { t } = useI18n();

  return (
    <div className="flex items-center gap-1.5">
      {switchable && !mobile && <LayoutToggle layout={layout} onChange={onChangeLayout} />}
      <ThemeToggle />
      {!mobile && <LanguageSelect />}
      <UserMenu />
      {mobile && onToggleMobile && (
        <button
          type="button"
          onClick={onToggleMobile}
          title={t(mobileOpen ? "common.close" : "layout.nav.open")}
          aria-label={t(mobileOpen ? "common.close" : "layout.nav.open")}
          aria-expanded={mobileOpen}
          aria-controls="mobile-navigation-drawer"
          className="control-glow grid h-9 w-9 place-items-center rounded-lg border border-border/80 bg-muted/45 text-muted-foreground shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
        >
          {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      )}
    </div>
  );
}
