"use client";

import { useEffect, useState } from "react";
import { ArrowRightLeft, Check, Copy, Database, FileJson } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import type { MigrationConfigResponse } from "@/lib/types";

export function AdminMigrationPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const [config, setConfig] = useState<MigrationConfigResponse | null>(null);
  const [mode, setMode] = useState<"file" | "database">("database");
  const [copied, setCopied] = useState<string | null>(null);

  // The locale/toast helpers are stable for the lifetime of the admin page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    void NyaApi.migrationConfig().then((value) => { setConfig(value); setMode(value.metadata_mode === "file" ? "file" : "database"); }).catch((error) => toast.error(error instanceof Error ? error.message : t("admin.migration.loadFailed")));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveMode() {
    try { const value = await NyaApi.updateMigrationConfig(mode); setConfig((current) => current ? { ...current, metadata_mode: value.metadata_mode } : current); toast.success(t("admin.migration.saved")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.migration.saveFailed")); }
  }

  async function copyCommand(value: string) {
    await navigator.clipboard.writeText(value); setCopied(value); window.setTimeout(() => setCopied(null), 1200); toast.success(t("common.copied"));
  }

  return <div className="space-y-6">
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div><h2 className="flex items-center gap-2 text-sm font-medium"><ArrowRightLeft className="h-4 w-4" />{t("admin.migration.primaryTitle")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.migration.primaryHint")}</p></div>
      <div className="flex flex-wrap items-end gap-3"><label className="space-y-1.5 text-xs"><span className="block font-medium">{t("admin.migration.primaryMode")}</span><select value={mode} onChange={(event) => setMode(event.target.value as "file" | "database")} className="h-9 rounded-md border border-input bg-background px-3 text-sm"><option value="database">database</option><option value="file">file</option></select></label><Button onClick={saveMode}>{t("admin.migration.saveMode")}</Button></div>
      {config && <p className="text-xs text-muted-foreground">{t("admin.migration.configPath")}: <code>{config.config_path}</code></p>}
    </section>
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm"><div><h2 className="flex items-center gap-2 text-sm font-medium"><Database className="h-4 w-4" />{t("admin.migration.sourcesTitle")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.migration.sourcesHint")}</p></div><div className="flex flex-wrap gap-2">{(config?.sources ?? []).map((source) => <span key={source} className="rounded-md border border-border px-2 py-1 text-xs">{source}</span>)}</div></section>
    <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm"><h2 className="flex items-center gap-2 text-sm font-medium"><FileJson className="h-4 w-4" />{t("admin.migration.commandsTitle")}</h2>{Object.entries(config?.commands ?? {}).map(([name, command]) => <div key={name} className="flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3"><div className="min-w-0 flex-1"><div className="mb-1 text-xs font-medium">{t(`admin.migration.commands.${name}`)}</div><code className="block break-all text-[11px]">{command}</code></div><Button variant="ghost" size="icon" title={t("common.copyLink")} onClick={() => void copyCommand(command)}>{copied === command ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</Button></div>)}</section>
  </div>;
}
