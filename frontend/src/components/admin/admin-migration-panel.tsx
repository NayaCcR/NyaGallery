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
  const [importJobs, setImportJobs] = useState<Array<{ job_id: string; source_type: string; status: string; total: number; cursor: number; succeeded: number; failed: number; progress: number; errors: string[] }>>([]);
  const [sourceType, setSourceType] = useState("url_list");

  // The locale/toast helpers are stable for the lifetime of the admin page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    void NyaApi.migrationConfig().then((value) => { setConfig(value); setMode(value.metadata_mode === "file" ? "file" : "database"); }).catch((error) => toast.error(error instanceof Error ? error.message : t("admin.migration.loadFailed")));
    void NyaApi.importJobs().then((value) => setImportJobs(value.items)).catch(() => undefined);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveMode() {
    try { const value = await NyaApi.updateMigrationConfig(mode); setConfig((current) => current ? { ...current, metadata_mode: value.metadata_mode } : current); toast.success(t("admin.migration.saved")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.migration.saveFailed")); }
  }

  async function createImport() { try { const job = await NyaApi.createImportJob(sourceType); setImportJobs((current) => [{ ...job, source_type: sourceType, total: 0, cursor: 0, succeeded: 0, failed: 0, progress: 0, errors: [] }, ...current]); toast.success(t("admin.migration.importCreated")); } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.migration.importFailed")); } }
  async function actImport(jobId: string, action: "pause" | "resume" | "retry_failed") { try { const job = await NyaApi.importJobAction(jobId, action); setImportJobs((current) => current.map((item) => item.job_id === jobId ? { ...item, ...job } : item)); } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.migration.importFailed")); } }

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
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm"><div><h2 className="text-sm font-medium">{t("admin.migration.importJobs")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.migration.importJobsHint")}</p></div><div className="flex gap-2"><select value={sourceType} onChange={(event) => setSourceType(event.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="url_list">URL list</option><option value="local_directory">Local directory</option></select><Button onClick={() => void createImport()}>{t("admin.migration.createImport")}</Button></div><div className="divide-y divide-border">{importJobs.map((job) => <div key={job.job_id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-xs"><div><code>{job.job_id}</code><span className="ml-2 text-muted-foreground">{job.source_type} · {job.status} · {Math.round(job.progress)}%</span></div><div className="flex gap-2">{job.status === "running" ? <Button variant="outline" size="sm" onClick={() => void actImport(job.job_id, "pause")}>{t("admin.migration.pause")}</Button> : <Button variant="outline" size="sm" onClick={() => void actImport(job.job_id, job.status === "failed" ? "retry_failed" : "resume")}>{t("admin.migration.resume")}</Button>}</div></div>)}</div></section>
    <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm"><h2 className="flex items-center gap-2 text-sm font-medium"><FileJson className="h-4 w-4" />{t("admin.migration.commandsTitle")}</h2>{Object.entries(config?.commands ?? {}).map(([name, command]) => <div key={name} className="flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3"><div className="min-w-0 flex-1"><div className="mb-1 text-xs font-medium">{t(`admin.migration.commands.${name}`)}</div><code className="block break-all text-[11px]">{command}</code></div><Button variant="ghost" size="icon" title={t("common.copyLink")} onClick={() => void copyCommand(command)}>{copied === command ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</Button></div>)}</section>
  </div>;
}
