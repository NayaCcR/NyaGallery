"use client";

import { useI18n } from "@/components/providers/locale-provider";
import { LayoutControl } from "@/components/layout/layout-control";
import { NavLink } from "@/components/layout/shell-parts";
import { LanguageSelect } from "@/components/layout/language-select";
import type { ShellModel } from "@/components/layout/shell-model";

export function MobileDrawer({ model }: { model: ShellModel }) {
  const { t } = useI18n();
  if (!model.mobileOpen) return null;

  return (
    <>
      <button
        type="button"
        onClick={model.onCloseMobile}
        aria-label={t("common.close")}
        className="fixed inset-0 top-16 z-30 bg-slate-950/35 backdrop-blur-[1px] lg:hidden"
      />
      <aside
        id="mobile-navigation-drawer"
        aria-label={t("layout.nav.open")}
        className="mobile-drawer fixed inset-x-3 top-16 z-40 grid max-h-[calc(100vh-5rem)] gap-5 overflow-y-auto rounded-b-xl border border-border/80 bg-popover/95 p-4 text-popover-foreground shadow-2xl backdrop-blur-xl lg:hidden"
      >
        <nav className="space-y-5">
          {model.groups.map((group) => (
            <div key={group.id} className="space-y-1">
              <div className="px-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{group.label}</div>
              {group.items.map((item) => (
                <NavLink key={item.href} href={item.href} active={item.active} icon={item.icon} label={item.label} onClick={model.onCloseMobile} />
              ))}
              {group.id === "workspace" && model.showAdminSubnav && (
                <div className="ml-4 mt-1 space-y-1 border-l border-border pl-2">
                  {model.adminItems.map((item) => (
                    <NavLink key={item.href} href={item.href} active={item.active} icon={item.icon} label={item.label} nested onClick={model.onCloseMobile} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
        <div className="grid gap-3 border-t border-border/80 pt-4">
          <LanguageSelect />
          {model.layoutSwitchable && <LayoutControl value={model.layout} onChange={model.onChangeLayout} />}
        </div>
      </aside>
    </>
  );
}
