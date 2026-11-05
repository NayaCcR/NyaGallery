"use client";

import { Activity, Ban, CalendarDays, Download, Gauge, History, ListChecks, RefreshCw, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyLine } from "@/components/admin/admin-fields";
import {
  TranscodeJobRow,
  UploadHistoryRow,
  UploadLogRow,
} from "@/components/admin/admin-operation-rows";
import { useI18n } from "@/components/providers/locale-provider";
import { formatDate, terminalStatus } from "@/components/admin/admin-format";
import { cn } from "@/lib/utils";
import type { TranscodeJob, UploadHistoryItem, UploadLogItem } from "@/lib/types";

type AdminPollingMode = "active" | "idle" | "paused";

const TRANSCODE_STATUSES = ["all", "queued", "running", "success", "error"] as const;
type TranscodeStatusFilter = (typeof TRANSCODE_STATUSES)[number];

/** Local calendar date (YYYY-MM-DD) of an ISO timestamp, matching what <input type="date"> yields. */
function localDateKey(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const chipDot: Record<TranscodeStatusFilter, string> = {
  all: "bg-muted-foreground/60",
  queued: "bg-amber-500",
  running: "bg-primary",
  success: "bg-emerald-500",
  error: "bg-destructive",
};

type AdminOperationsPanelProps = {
  isAdmin: boolean;
  busy: string | null;
  error: string | null;
  pollingMode: AdminPollingMode;
  lastUpdatedAt: string | null;
  transcodeJobs: TranscodeJob[];
  uploadHistory: UploadHistoryItem[];
  uploadLogs: UploadLogItem[];
  onRefresh: () => unknown;
  onStartTranscode: (assetKey: string) => unknown;
  onRetryTranscodeBatch: (assetKeys: string[]) => unknown;
  onCancelAllTranscode: () => unknown;
};

export function AdminOperationsPanel({
  isAdmin,
  busy,
  error,
  pollingMode,
  lastUpdatedAt,
  transcodeJobs,
  uploadHistory,
  uploadLogs,
  onRefresh,
  onStartTranscode,
  onRetryTranscodeBatch,
  onCancelAllTranscode,
}: AdminOperationsPanelProps) {
  const { t } = useI18n();
  const [logQuery, setLogQuery] = useState("");
  const [logStatus, setLogStatus] = useState("all");
  const [transcodeStatus, setTranscodeStatus] = useState<TranscodeStatusFilter>("all");
  const [transcodeFrom, setTranscodeFrom] = useState("");
  const [transcodeTo, setTranscodeTo] = useState("");
  const [selectedTranscodeJobs, setSelectedTranscodeJobs] = useState<Set<string>>(() => new Set());
  const dateFilteredTranscodeJobs = useMemo(() => {
    const [from, to] = transcodeFrom && transcodeTo && transcodeFrom > transcodeTo ? [transcodeTo, transcodeFrom] : [transcodeFrom, transcodeTo];
    return transcodeJobs.filter((job) => {
      if (!from && !to) return true;
      const day = localDateKey(job.created_at || job.updated_at);
      return Boolean(day) && (!from || day >= from) && (!to || day <= to);
    });
  }, [transcodeFrom, transcodeTo, transcodeJobs]);
  const transcodeStatusCounts = useMemo(() => {
    const counts: Record<TranscodeStatusFilter, number> = { all: dateFilteredTranscodeJobs.length, queued: 0, running: 0, success: 0, error: 0 };
    for (const job of dateFilteredTranscodeJobs) {
      const status = terminalStatus(job) as TranscodeStatusFilter;
      if (status in counts && status !== "all") counts[status] += 1;
    }
    return counts;
  }, [dateFilteredTranscodeJobs]);
  const filteredTranscodeJobs = useMemo(
    () => (transcodeStatus === "all" ? dateFilteredTranscodeJobs : dateFilteredTranscodeJobs.filter((job) => terminalStatus(job) === transcodeStatus)),
    [dateFilteredTranscodeJobs, transcodeStatus]
  );
  const failedTranscodeJobs = useMemo(() => filteredTranscodeJobs.filter((job) => terminalStatus(job) === "error"), [filteredTranscodeJobs]);
  // Drop selections that are filtered out or no longer failed, so the count always matches what will be retried.
  useEffect(() => {
    setSelectedTranscodeJobs((current) => {
      if (current.size === 0) return current;
      const visible = new Set(failedTranscodeJobs.map((job) => job.job_id));
      const next = new Set(Array.from(current).filter((id) => visible.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [failedTranscodeJobs]);
  const selectedFailedJobs = failedTranscodeJobs.filter((job) => selectedTranscodeJobs.has(job.job_id));
  const selectedCount = selectedFailedJobs.length;
  const allFailedSelected = failedTranscodeJobs.length > 0 && selectedCount === failedTranscodeJobs.length;
  const someFailedSelected = selectedCount > 0 && !allFailedSelected;
  const transcodeFiltersActive = transcodeStatus !== "all" || Boolean(transcodeFrom) || Boolean(transcodeTo);
  const batchBusy = busy === "transcode-batch";
  const toggleTranscodeJob = (jobId: string) => setSelectedTranscodeJobs((current) => {
    const next = new Set(current);
    if (next.has(jobId)) next.delete(jobId); else next.add(jobId);
    return next;
  });
  const toggleAllFailed = () => setSelectedTranscodeJobs(allFailedSelected ? new Set() : new Set(failedTranscodeJobs.map((job) => job.job_id)));
  const clearTranscodeFilters = () => {
    setTranscodeStatus("all");
    setTranscodeFrom("");
    setTranscodeTo("");
  };
  const retrySelected = async () => {
    const assetKeys = selectedFailedJobs.map((job) => job.asset_key);
    if (assetKeys.length === 0) return;
    await Promise.resolve(onRetryTranscodeBatch(assetKeys));
    setSelectedTranscodeJobs(new Set());
  };
  const dateInputClass = "h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs text-foreground focus-ring [color-scheme:light] dark:[color-scheme:dark] sm:w-[9.5rem] sm:flex-none";
  const filteredLogs = useMemo(() => uploadLogs.filter((log) => {
    const haystack = JSON.stringify(log).toLowerCase();
    return (logStatus === "all" || log.status === logStatus) && (!logQuery.trim() || haystack.includes(logQuery.trim().toLowerCase()));
  }), [logQuery, logStatus, uploadLogs]);
  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(filteredLogs, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "nyagallery-upload-logs.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4" /> {t("admin.ops.title")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {isAdmin ? t("admin.ops.scopeAdmin") : t("admin.ops.scopeOwn")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-border bg-muted/40 px-2 py-1 text-[11px] text-muted-foreground">
            {pollingMode === "active" && t("admin.ops.pollingActive")}
            {pollingMode === "idle" && t("admin.ops.pollingIdle")}
            {pollingMode === "paused" && t("admin.ops.pollingPaused")}
            {lastUpdatedAt && (
              <span className="hidden sm:inline">
                {" · "}
                {t("admin.ops.lastUpdated", { time: formatDate(lastUpdatedAt) })}
              </span>
            )}
          </span>
          <Button variant="outline" size="sm" disabled={busy === "ops-refresh"} onClick={onRefresh}>
            <RefreshCw className="h-4 w-4" /> {t("admin.ops.refresh")}
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <Gauge className="h-3.5 w-3.5" /> {t("admin.ops.transcodeJobs")}
            {transcodeJobs.some((j) => j.status === "queued" || j.status === "running") && (
              <button
                type="button"
                disabled={busy === "cancel-all-transcode"}
                onClick={onCancelAllTranscode}
                className="ml-auto inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] font-normal normal-case text-destructive hover:bg-destructive/5 disabled:opacity-50"
              >
                <Ban className="h-3 w-3" /> {t("admin.ops.cancelAll")}
              </button>
            )}
          </h3>
          <div className="space-y-2.5 rounded-lg border border-border bg-muted/25 p-2.5">
            <div role="radiogroup" aria-label={t("admin.ops.transcodeStatus")} className="flex flex-wrap gap-1.5">
              {TRANSCODE_STATUSES.map((status) => {
                const active = transcodeStatus === status;
                return (
                  <button
                    key={status}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setTranscodeStatus(status)}
                    className={cn(
                      "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors focus-ring",
                      active
                        ? "border-primary/50 bg-primary/10 font-medium text-foreground"
                        : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    <span className={cn("h-1.5 w-1.5 rounded-full", chipDot[status])} />
                    {status === "all" ? t("admin.ops.allTranscodeStatuses") : t(`admin.logs.statuses.${status}`)}
                    <span className={cn("tabular-nums", active ? "text-foreground/70" : "text-muted-foreground/70")}>{transcodeStatusCounts[status]}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <CalendarDays className="h-3.5 w-3.5" /> {t("admin.ops.dateRange")}
              </span>
              <div className="flex min-w-0 flex-1 items-center gap-1.5 sm:flex-none">
                <input type="date" value={transcodeFrom} max={transcodeTo || undefined} onChange={(event) => setTranscodeFrom(event.target.value)} className={dateInputClass} aria-label={t("admin.ops.transcodeFrom")} title={t("admin.ops.transcodeFrom")} />
                <span className="text-xs text-muted-foreground">–</span>
                <input type="date" value={transcodeTo} min={transcodeFrom || undefined} onChange={(event) => setTranscodeTo(event.target.value)} className={dateInputClass} aria-label={t("admin.ops.transcodeTo")} title={t("admin.ops.transcodeTo")} />
              </div>
              <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                <span className="tabular-nums" title={t("admin.ops.transcodeRecentHint", { count: transcodeJobs.length })}>
                  {t("admin.ops.transcodeResults", { shown: filteredTranscodeJobs.length, total: transcodeJobs.length })}
                </span>
                {transcodeFiltersActive && (
                  <button type="button" onClick={clearTranscodeFilters} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-muted hover:text-foreground focus-ring">
                    <X className="h-3 w-3" /> {t("admin.ops.clearFilters")}
                  </button>
                )}
              </div>
            </div>
            {failedTranscodeJobs.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 border-t border-border/70 pt-2.5">
                <label className="inline-flex cursor-pointer select-none items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    ref={(node) => { if (node) node.indeterminate = someFailedSelected; }}
                    checked={allFailedSelected}
                    onChange={toggleAllFailed}
                    className="h-4 w-4 cursor-pointer rounded border-border accent-primary"
                  />
                  {t("admin.ops.selectFailed")}
                </label>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {t("admin.ops.selectedFailed", { selected: selectedCount, failed: failedTranscodeJobs.length })}
                </span>
                <div className="ml-auto flex items-center gap-1.5">
                  {selectedCount > 0 && (
                    <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setSelectedTranscodeJobs(new Set())}>
                      {t("admin.ops.clearSelection")}
                    </Button>
                  )}
                  <Button type="button" size="sm" variant={selectedCount > 0 ? "default" : "outline"} className="h-7 px-2.5 text-xs" disabled={selectedCount === 0 || batchBusy} onClick={() => void retrySelected()}>
                    <RotateCcw className={cn("h-3.5 w-3.5", batchBusy && "animate-spin")} /> {t("admin.ops.retrySelected")} ({selectedCount})
                  </Button>
                </div>
              </div>
            )}
          </div>
          <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {filteredTranscodeJobs.map((job) => (
              <TranscodeJobRow
                key={job.job_id}
                job={job}
                selected={selectedTranscodeJobs.has(job.job_id)}
                busy={batchBusy || busy === `transcode-${job.asset_key}`}
                onToggle={() => toggleTranscodeJob(job.job_id)}
                onRetry={() => void Promise.resolve(onStartTranscode(job.asset_key))}
              />
            ))}
            {filteredTranscodeJobs.length === 0 && (
              <div className="space-y-2 rounded-lg border border-dashed border-border p-4 text-center">
                <EmptyLine text={t("admin.ops.emptyTranscode")} />
                {transcodeFiltersActive && transcodeJobs.length > 0 && (
                  <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={clearTranscodeFilters}>
                    {t("admin.ops.clearFilters")}
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <History className="h-3.5 w-3.5" /> {t("admin.ops.uploadHistory")}
          </h3>
          <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {uploadHistory.map((item) => (
              <UploadHistoryRow
                key={item.asset_key}
                item={item}
                busy={busy === `transcode-${item.asset_key}`}
                onStartTranscode={() => onStartTranscode(item.asset_key)}
              />
            ))}
            {uploadHistory.length === 0 && <EmptyLine text={t("admin.ops.emptyUploads")} />}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <ListChecks className="h-3.5 w-3.5" /> {t("admin.ops.recentLogs")}
          </h3>
          <Button variant="outline" size="sm" onClick={exportLogs} disabled={filteredLogs.length === 0}>
            <Download className="h-4 w-4" /> {t("admin.ops.exportLogs")}
          </Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_160px]">
          <input value={logQuery} onChange={(event) => setLogQuery(event.target.value)} placeholder={t("admin.ops.searchLogs")} className="h-9 rounded-md border border-input bg-transparent px-3 text-sm focus-ring" />
          <select value={logStatus} onChange={(event) => setLogStatus(event.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm">
            <option value="all">{t("admin.ops.allLogStatuses")}</option>
            <option value="success">{t("admin.logs.statuses.success")}</option>
            <option value="error">{t("admin.logs.statuses.error")}</option>
            <option value="queued">{t("admin.logs.statuses.queued")}</option>
            <option value="running">{t("admin.logs.statuses.running")}</option>
          </select>
        </div>
        <div className="max-h-72 overflow-auto rounded-lg border border-border">
          {filteredLogs.map((log) => (
            <UploadLogRow key={log.id} log={log} />
          ))}
          {filteredLogs.length === 0 && <div className="p-6 text-center text-sm text-muted-foreground">{t("admin.ops.emptyLogs")}</div>}
        </div>
      </div>
    </section>
  );
}
