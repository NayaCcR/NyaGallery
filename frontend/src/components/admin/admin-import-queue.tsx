"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FolderInput, Link2, ListChecks, Loader2, Pause, Play, Plus, RotateCcw, Trash2 } from "lucide-react";
import { SegmentedControl, SyncCard, SyncNotice, SyncSwitchGroup } from "@/components/admin/admin-sync-shared";
import { EmptyLine } from "@/components/admin/admin-fields";
import { formatDate } from "@/components/admin/admin-format";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SwitchLabel } from "@/components/ui/switch-label";
import { NyaApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ImportConfigResponse, ImportJob } from "@/lib/types";

type Source = "local_directory" | "url_list";
const ACTIVE = new Set(["queued", "running"]);

/** Web import queue: create a job (allowed server folder or URL list) and watch it run in the background. */
export function AdminImportQueue() {
  const { t } = useI18n();
  const toast = useToast();
  const [config, setConfig] = useState<ImportConfigResponse | null>(null);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [source, setSource] = useState<Source>("local_directory");
  const [path, setPath] = useState("");
  const [urls, setUrls] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [makePublic, setMakePublic] = useState(false);
  const [generateCache, setGenerateCache] = useState(true);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busyJob, setBusyJob] = useState<string | null>(null);
  const toastRef = useRef(toast);
  toastRef.current = toast;

  const refresh = useCallback(async () => {
    try {
      setJobs((await NyaApi.importJobs()).items);
    } catch {
      /* keep last list */
    }
  }, []);

  useEffect(() => {
    NyaApi.importConfig()
      .then((value) => {
        setConfig(value);
        if (value.allowed_roots.length === 0) setSource("url_list");
        else setPath(value.allowed_roots[0]);
      })
      .catch((error) => toastRef.current.error(error instanceof Error ? error.message : String(error)));
    void refresh();
  }, [refresh]);

  // Poll while something is queued or running.
  const hasActive = jobs.some((job) => ACTIVE.has(job.status));
  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [hasActive, refresh]);

  const localDisabled = (config?.allowed_roots.length ?? 0) === 0;
  const canCreate = source === "local_directory" ? Boolean(path.trim()) && !localDisabled : Boolean(urls.trim());

  async function create() {
    setCreating(true);
    try {
      const sourceConfig: Record<string, unknown> = { visibility: makePublic ? "public" : "private", generate_cache: generateCache, skip_duplicates: skipDuplicates };
      if (source === "local_directory") Object.assign(sourceConfig, { path: path.trim(), recursive });
      else sourceConfig.urls = urls.split(/\s+/).filter(Boolean);
      const job = await NyaApi.createImportJob(source, sourceConfig);
      setJobs((current) => [job, ...current]);
      if (source === "url_list") setUrls("");
      toast.success(t("admin.importQueue.created"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      setCreating(false);
    }
  }

  async function act(job: ImportJob, action: "pause" | "resume" | "retry_failed" | "delete") {
    setBusyJob(job.job_id);
    try {
      if (action === "delete") {
        await NyaApi.deleteImportJob(job.job_id);
        setJobs((current) => current.filter((item) => item.job_id !== job.job_id));
      } else {
        const updated = await NyaApi.importJobAction(job.job_id, action);
        setJobs((current) => current.map((item) => (item.job_id === job.job_id ? updated : item)));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyJob(null);
    }
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
      <SyncCard icon={Plus} title={t("admin.importQueue.newJob")} description={t("admin.importQueue.newJobHint")}>
        <SegmentedControl
          value={source}
          onChange={setSource}
          options={[
            { value: "local_directory" as Source, label: t("admin.importQueue.sources.local_directory"), disabled: localDisabled },
            { value: "url_list" as Source, label: t("admin.importQueue.sources.url_list") },
          ]}
        />
        {source === "local_directory" ? (
          <div className="space-y-1.5">
            <Label>{t("admin.importQueue.folder")}</Label>
            <Input value={path} onChange={(event) => setPath(event.target.value)} placeholder={config?.allowed_roots[0] ?? ""} className="font-mono text-xs" />
            <p className="text-[11px] leading-5 text-muted-foreground">
              {t("admin.importQueue.allowedRoots")}{" "}
              {(config?.allowed_roots ?? []).map((root) => (
                <button key={root} type="button" onClick={() => setPath(root)} className="mr-1 rounded border border-border px-1 font-mono hover:bg-muted">
                  {root}
                </button>
              ))}
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label>{t("admin.importQueue.urls")}</Label>
            <textarea
              value={urls}
              onChange={(event) => setUrls(event.target.value)}
              placeholder={"https://example.com/a.png\nhttps://example.com/b.jpg"}
              className="flex min-h-[110px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs focus-ring"
            />
            <p className="text-[11px] text-muted-foreground">{t("admin.importQueue.urlsHint")}</p>
          </div>
        )}
        {localDisabled && <SyncNotice tone="info">{t("admin.importQueue.noRoots")}</SyncNotice>}
        <SyncSwitchGroup>
          {source === "local_directory" && <SwitchLabel label={t("admin.importQueue.recursive")} checked={recursive} onChange={setRecursive} />}
          <SwitchLabel label={t("admin.importQueue.makePublic")} checked={makePublic} onChange={setMakePublic} />
          <SwitchLabel label={t("admin.importQueue.generateCache")} checked={generateCache} onChange={setGenerateCache} />
          <SwitchLabel label={t("admin.importQueue.skipDuplicates")} checked={skipDuplicates} onChange={setSkipDuplicates} />
        </SyncSwitchGroup>
        <Button className="w-full" disabled={!canCreate || creating} onClick={() => void create()}>
          {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : source === "local_directory" ? <FolderInput className="h-4 w-4" /> : <Link2 className="h-4 w-4" />} {t("admin.importQueue.start")}
        </Button>
      </SyncCard>

      <SyncCard icon={ListChecks} title={t("admin.importQueue.jobs", { count: jobs.length })} description={t("admin.importQueue.jobsHint")}>
        {jobs.length === 0 ? (
          <EmptyLine text={t("admin.migration.emptyJobs")} />
        ) : (
          <div className="max-h-[640px] space-y-2 overflow-auto pr-1">
            {jobs.map((job) => (
              <JobRow key={job.job_id} job={job} busy={busyJob === job.job_id} onAction={(action) => void act(job, action)} />
            ))}
          </div>
        )}
      </SyncCard>
    </div>
  );
}

function JobRow({ job, busy, onAction }: { job: ImportJob; busy: boolean; onAction: (action: "pause" | "resume" | "retry_failed" | "delete") => void }) {
  const { t } = useI18n();
  const progress = Math.max(0, Math.min(100, Math.round(job.progress || 0)));
  const running = job.status === "running";
  const failedRun = job.status === "failed" || job.failed > 0;
  return (
    <div className={cn("space-y-2 rounded-lg border border-border p-3 text-xs", failedRun && "border-destructive/35", running && "border-primary/40")}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-medium">{t(`admin.importQueue.sources.${job.source_type}`)}</span>
            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", running ? "bg-primary/10 text-primary" : job.status === "succeeded" ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : job.status === "failed" ? "bg-destructive/10 text-destructive" : "bg-muted")}>
              {running && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
              {t(`admin.migration.jobStatus.${job.status}`)}
            </span>
          </div>
          <div className="truncate font-mono text-[11px] text-muted-foreground">
            {job.job_id}
            {job.created_at ? ` · ${formatDate(job.created_at)}` : ""}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {(job.status === "running" || job.status === "queued") && (
            <Button variant="outline" size="sm" className="h-7 px-2 text-xs" disabled={busy} onClick={() => onAction("pause")}>
              <Pause className="h-3.5 w-3.5" /> {t("admin.migration.pause")}
            </Button>
          )}
          {job.status === "paused" && (
            <Button variant="outline" size="sm" className="h-7 px-2 text-xs" disabled={busy} onClick={() => onAction("resume")}>
              <Play className="h-3.5 w-3.5" /> {t("admin.migration.resume")}
            </Button>
          )}
          {(job.status === "failed" || job.status === "succeeded") && job.failed_indices.length > 0 && (
            <Button variant="outline" size="sm" className="h-7 px-2 text-xs" disabled={busy} onClick={() => onAction("retry_failed")}>
              <RotateCcw className="h-3.5 w-3.5" /> {t("admin.importQueue.retryFailed", { count: job.failed_indices.length })}
            </Button>
          )}
          {job.status !== "running" && (
            <Button variant="ghost" size="sm" className="h-7 px-2 text-destructive hover:bg-destructive/10 hover:text-destructive" disabled={busy} onClick={() => onAction("delete")} aria-label={t("admin.importQueue.delete")} title={t("admin.importQueue.delete")}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", job.failed > 0 && job.succeeded === 0 ? "bg-destructive" : "bg-primary")} style={{ width: `${progress}%` }} />
      </div>
      <div className="flex flex-wrap gap-x-3 text-[11px] tabular-nums text-muted-foreground">
        <span>{progress}%</span>
        <span>{job.cursor}/{job.total}</span>
        <span className="text-emerald-600 dark:text-emerald-400">{t("admin.migration.succeededCount", { count: job.succeeded })}</span>
        <span className={cn(job.failed > 0 && "text-destructive")}>{t("admin.migration.failedCount", { count: job.failed })}</span>
      </div>
      {job.errors.length > 0 && (
        <details className="text-[11px]">
          <summary className="cursor-pointer text-destructive">{t("admin.importQueue.errors", { count: job.errors.length })}</summary>
          <ul className="mt-1 max-h-32 space-y-0.5 overflow-auto font-mono text-destructive">
            {job.errors.slice(-20).map((error, index) => (
              <li key={index} className="break-words">{error}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
