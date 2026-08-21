"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { BrandLogo } from "@/components/layout/brand-logo";
import { MobileDrawer } from "@/components/layout/mobile-drawer";
import { ShellActions } from "@/components/layout/shell-actions";
import { NavLink, ShellFooter } from "@/components/layout/shell-parts";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
import type { ShellModel } from "@/components/layout/shell-model";

/** Fixed left rail with a compact desktop tools row and no desktop top-shell. */
export function SidebarShell({ model, children }: { model: ShellModel; children: React.ReactNode }) {
  const { t } = useI18n();
  const { branding } = model;
  const CollapseIcon = model.sidebarCollapsed ? PanelLeftOpen : PanelLeftClose;
  const collapseLabel = t(model.sidebarCollapsed ? "layout.sidebar.expand" : "layout.sidebar.collapse");

  return (
    <div className="min-h-screen text-foreground">
      <aside
        aria-label={t("layout.header.workspace")}
        className={cn(
          "side-shell fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-border/80 bg-card/75 backdrop-blur-xl transition-[width] duration-200 lg:flex",
          model.sidebarCollapsed ? "is-collapsed w-20" : "w-64"
        )}
      >
        <div className={cn("border-b border-border/80 px-4 py-5", model.sidebarCollapsed && "flex justify-center px-2")}>
          <BrandLogo
            branding={branding}
            variant="sidebar"
            subtitle={t("layout.header.console")}
            showWordmark={!model.sidebarCollapsed}
            className={model.sidebarCollapsed ? "justify-center" : undefined}
          />
        </div>

        <nav className={cn("flex-1 space-y-5 overflow-y-auto py-5", model.sidebarCollapsed ? "px-2" : "px-3")}>
          {model.groups.map((group) => (
            <div key={group.id} className="space-y-1">
              {!model.sidebarCollapsed && (
                <div className="px-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{group.label}</div>
              )}
              {group.items.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  active={item.active}
                  icon={item.icon}
                  label={item.label}
                  collapsed={model.sidebarCollapsed}
                />
              ))}
              {group.id === "workspace" && model.showAdminSubnav && (
                <div className={cn("ml-4 mt-1 space-y-1 border-l border-border pl-2", model.sidebarCollapsed && "ml-0 border-l-0 pl-0")}>
                  {model.adminItems.map((item) => (
                    <NavLink
                      key={item.href}
                      href={item.href}
                      active={item.active}
                      icon={item.icon}
                      label={item.label}
                      nested
                      collapsed={model.sidebarCollapsed}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>

        <div className={cn("border-t border-border/80 p-3", model.sidebarCollapsed && "px-2")}>
          {!model.sidebarCollapsed && <p className="mb-3 px-2 text-[11px] leading-5 text-muted-foreground">{t("layout.header.workspace")}</p>}
          <button
            type="button"
            onClick={() => model.onCollapseSidebar(!model.sidebarCollapsed)}
            title={collapseLabel}
            aria-label={collapseLabel}
            aria-pressed={model.sidebarCollapsed}
            className={cn(
              "control-glow flex h-10 w-full items-center gap-3 rounded-lg border border-border/80 bg-muted/35 px-3 text-sm font-medium text-muted-foreground shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary",
              model.sidebarCollapsed && "justify-center px-0"
            )}
          >
            <CollapseIcon className={cn("shrink-0", model.sidebarCollapsed ? "h-5 w-5" : "h-4 w-4")} />
            <span className={model.sidebarCollapsed ? "sr-only" : undefined}>{collapseLabel}</span>
          </button>
        </div>
      </aside>

      <header className="mobile-top-shell sticky top-0 z-30 flex min-h-16 items-center justify-between border-b border-border/80 bg-background/75 px-4 backdrop-blur-xl lg:hidden">
        <BrandLogo branding={branding} variant="topbar" />
        <div className="flex items-center"><ShellActions layout={model.layout} switchable={model.layoutSwitchable} onChangeLayout={model.onChangeLayout} mobile mobileOpen={model.mobileOpen} onToggleMobile={model.onToggleMobile} /></div>
      </header>
      <MobileDrawer model={model} />

      <div className={cn("min-h-screen transition-[padding] duration-200", model.sidebarCollapsed ? "lg:pl-20" : "lg:pl-64")}>
        {/* Sidebar mode intentionally keeps only this compact action row on desktop. */}
        <div className="desktop-page-tools hidden h-16 items-center justify-between border-b border-border/80 px-6 lg:flex">
          <span className="text-xs text-muted-foreground">
            {t("layout.header.workspace")} <span className="px-1 text-border">/</span> {model.headerTitle}
          </span>
          <div className="desktop-shell-actions flex items-center rounded-lg border border-border/80 bg-muted/45 p-1 shadow-sm">
            <ShellActions layout={model.layout} switchable={model.layoutSwitchable} onChangeLayout={model.onChangeLayout} />
          </div>
        </div>
        <main className="min-h-[calc(100vh-4rem)] bg-transparent">{children}</main>
        <ShellFooter
          branding={branding}
          repositoryUrl={model.repositoryUrl}
          icpBeian={model.icpBeian}
          className="lg:border-l"
        />
      </div>
    </div>
  );
}
