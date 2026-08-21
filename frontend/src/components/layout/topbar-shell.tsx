"use client";

import Link from "next/link";
import { BrandLogo } from "@/components/layout/brand-logo";
import { MobileDrawer } from "@/components/layout/mobile-drawer";
import { ShellActions } from "@/components/layout/shell-actions";
import { NavLink, ShellFooter } from "@/components/layout/shell-parts";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
import type { ShellModel, ShellNavItem } from "@/components/layout/shell-model";

const CONTAINER = "w-full px-4 lg:px-6";

/** Full-width shell with the template's right-side management controls. */
export function TopbarShell({ model, children }: { model: ShellModel; children: React.ReactNode }) {
  const { t } = useI18n();
  const { branding } = model;
  const primaryItems = model.groups.flatMap((group) => group.items);

  return (
    <div className="top-shell flex min-h-screen flex-col text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/70 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60">
        <div className={cn(CONTAINER, "flex min-h-16 items-center gap-3 py-2")}>
          <BrandLogo branding={branding} variant="topbar" className="shrink-0" />
          <span aria-hidden="true" className="hidden h-6 w-px shrink-0 bg-border md:block" />

          <nav className="scrollbar-none hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto md:flex">
            {primaryItems.map((item) => (
              <TopbarNavLink key={item.href} item={item} />
            ))}
          </nav>

          <div className="ml-auto shrink-0 md:ml-0">
            <div className="desktop-shell-actions hidden items-center rounded-lg border border-border/80 bg-muted/45 p-1 shadow-sm md:flex">
              <ShellActions layout={model.layout} switchable={model.layoutSwitchable} onChangeLayout={model.onChangeLayout} />
            </div>
            <div className="mobile-shell-actions flex items-center md:hidden">
              <ShellActions layout={model.layout} switchable={model.layoutSwitchable} onChangeLayout={model.onChangeLayout} mobile mobileOpen={model.mobileOpen} onToggleMobile={model.onToggleMobile} />
            </div>
          </div>
        </div>

        {model.showAdminSubnav && model.adminItems.length > 0 && (
          <div className="hidden border-t border-border/60 md:block">
            <nav className={cn(CONTAINER, "scrollbar-none flex h-11 items-center gap-0.5 overflow-x-auto")}>
              {model.adminItems.map((item) => (
                <TopbarNavLink key={item.href} item={item} subtle />
              ))}
            </nav>
          </div>
        )}
      </header>
      <MobileDrawer model={model} />

      <main className="flex-1">{children}</main>

      <ShellFooter branding={branding} repositoryUrl={model.repositoryUrl} icpBeian={model.icpBeian} />
    </div>
  );
}

function TopbarNavLink({ item, subtle = false }: { item: ShellNavItem; subtle?: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-lg font-medium transition-colors",
        subtle ? "h-8 px-2.5 text-xs" : "h-9 px-3 text-sm",
        item.active
          ? "bg-primary/10 text-primary shadow-sm"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
      )}
    >
      <Icon className={cn("shrink-0", subtle ? "h-3.5 w-3.5" : "h-4 w-4")} />
      <span className="whitespace-nowrap">{item.label}</span>
    </Link>
  );
}
