"use client";

import { useState } from "react";
import { AlertTriangle, BadgeCheck, Boxes, FolderOpen, Loader2, Puzzle, RefreshCw } from "lucide-react";
import { SyncCard, SyncNotice } from "@/components/admin/admin-sync-shared";
import { EmptyLine } from "@/components/admin/admin-fields";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { usePlugins } from "@/hooks/use-plugins";
import { NyaApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PluginItem } from "@/lib/types";

/** Admin -> Plugins: list official and third-party plugins and toggle them without a restart. */
export function AdminPluginsPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const plugins = usePlugins();
  const [busy, setBusy] = useState<string | null>(null);
  const items = plugins.data?.items ?? [];
  const official = items.filter((item) => item.official);
  const community = items.filter((item) => !item.official);

  async function toggle(item: PluginItem) {
    setBusy(item.name);
    try {
      const result = await NyaApi.setPluginEnabled(item.name, !item.enabled);
      if (plugins.data && result.item) {
        plugins.setData({
          ...plugins.data,
          disabled_sections: result.disabled_sections,
          items: plugins.data.items.map((entry) => (entry.name === item.name ? result.item! : entry)),
        });
      }
      toast.success(t(item.enabled ? "admin.plugins.disabledToast" : "admin.plugins.enabledToast", { name: item.title || item.name }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <SyncCard
        icon={Puzzle}
        title={t("admin.plugins.title")}
        description={t("admin.plugins.description", { version: plugins.data?.core_version ?? "?" })}
        actions={
          <Button variant="outline" size="sm" disabled={plugins.isFetching} onClick={() => void plugins.refetch()} aria-label={t("admin.ops.refresh")} title={t("admin.ops.refresh")}>
            <RefreshCw className={cn("h-4 w-4", plugins.isFetching && "animate-spin")} />
          </Button>
        }
      >
        {plugins.data && !plugins.data.available && <SyncNotice>{t("admin.plugins.unavailable")}</SyncNotice>}
        <SyncNotice tone="info">{t("admin.plugins.coreHint")}</SyncNotice>
      </SyncCard>

      <SyncCard icon={BadgeCheck} title={t("admin.plugins.official", { count: official.length })} description={t("admin.plugins.officialHint")}>
        {plugins.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {official.map((item) => <PluginCard key={item.name} item={item} busy={busy === item.name} onToggle={() => void toggle(item)} />)}
          </div>
        )}
      </SyncCard>

      <SyncCard icon={Boxes} title={t("admin.plugins.community", { count: community.length })} description={t("admin.plugins.communityHint")}>
        {community.length === 0 ? (
          <EmptyLine text={t("admin.plugins.communityEmpty")} />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {community.map((item) => <PluginCard key={item.name} item={item} busy={busy === item.name} onToggle={() => void toggle(item)} />)}
          </div>
        )}
        <div className="flex items-start gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
          <FolderOpen className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{t("admin.plugins.installHint")}</span>
        </div>
      </SyncCard>
    </div>
  );
}

function PluginCard({ item, busy, onToggle }: { item: PluginItem; busy: boolean; onToggle: () => void }) {
  const { t } = useI18n();
  const broken = Boolean(item.error) && !item.version;
  const blockedByDependents = item.enabled && item.dependents.length > 0;
  return (
    <div className={cn("space-y-3 rounded-lg border p-4 text-xs", item.enabled ? "border-primary/30" : "border-border bg-muted/20", item.error && "border-destructive/40")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium">{item.title || item.name}</span>
            {item.version && <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">v{item.version}</span>}
            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", item.enabled ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground")}>
              {item.enabled ? t("admin.plugins.on") : t("admin.plugins.off")}
            </span>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{item.name}</div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={item.enabled}
          aria-label={t(item.enabled ? "admin.plugins.disable" : "admin.plugins.enable", { name: item.title || item.name })}
          disabled={busy || broken || blockedByDependents}
          title={blockedByDependents ? t("admin.plugins.hasDependents", { names: item.dependents.join(", ") }) : undefined}
          onClick={onToggle}
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-ring disabled:cursor-not-allowed disabled:opacity-50",
            item.enabled ? "bg-primary" : "bg-muted-foreground/30"
          )}
        >
          {busy ? (
            <Loader2 className="mx-auto h-3.5 w-3.5 animate-spin text-white" />
          ) : (
            <span className={cn("inline-block h-5 w-5 rounded-full bg-white shadow transition-transform", item.enabled ? "translate-x-5" : "translate-x-0.5")} />
          )}
        </button>
      </div>
      {item.description && <p className="leading-5 text-muted-foreground">{item.description}</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px]">
        {item.plugin_types.length > 0 && (
          <>
            <dt className="text-muted-foreground">{t("admin.plugins.types")}</dt>
            <dd>{item.plugin_types.join(", ")}</dd>
          </>
        )}
        {item.permissions.length > 0 && (
          <>
            <dt className="text-muted-foreground">{t("admin.plugins.permissions")}</dt>
            <dd className="flex flex-wrap gap-1">
              {item.permissions.map((permission) => (
                <span key={permission} className="rounded border border-border px-1 font-mono text-[10px]">{permission}</span>
              ))}
            </dd>
          </>
        )}
        {item.dependencies.length > 0 && (
          <>
            <dt className="text-muted-foreground">{t("admin.plugins.dependencies")}</dt>
            <dd className="font-mono">{item.dependencies.join(", ")}</dd>
          </>
        )}
        <dt className="text-muted-foreground">{t("admin.plugins.provides")}</dt>
        <dd>
          {t("admin.plugins.providesValue", { routes: item.routes, events: item.events.length })}
          {item.provides_sections.length > 0 && ` · ${item.provides_sections.map((section) => t(`admin.sections.${section}`)).join(", ")}`}
        </dd>
        {!item.official && (
          <>
            <dt className="text-muted-foreground">{t("admin.plugins.source")}</dt>
            <dd className="truncate font-mono" title={item.source}>{item.source}</dd>
          </>
        )}
      </dl>
      {item.error && (
        <div className="flex items-start gap-1.5 rounded-md bg-destructive/10 px-2.5 py-1.5 text-[11px] text-destructive">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="break-words">{item.error}</span>
        </div>
      )}
    </div>
  );
}
