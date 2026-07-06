"use client";

import { Activity, Ban, Gauge, History, ListChecks, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyLine } from "@/components/admin/admin-fields";
import {
  TranscodeJobRow,
  UploadHistoryRow,
  UploadLogRow,
} from "@/components/admin/admin-operation-rows";
import { useI18n } from "@/components/providers/locale-provider";
import { formatDate } from "@/components/admin/admin-format";
import type { TranscodeJob, UploadHistoryItem, UploadLogItem } from "@/lib/types";

type AdminPollingMode = "active" | "idle" | "paused";

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
  onCancelAllTranscode,
}: AdminOperationsPanelProps) {
  const { t } = useI18n();

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
          <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {transcodeJobs.map((job) => (
              <TranscodeJobRow key={job.job_id} job={job} />
            ))}
            {transcodeJobs.length === 0 && <EmptyLine text={t("admin.ops.emptyTranscode")} />}
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
        <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
          <ListChecks className="h-3.5 w-3.5" /> {t("admin.ops.recentLogs")}
        </h3>
        <div className="max-h-72 overflow-auto rounded-lg border border-border">
          {uploadLogs.map((log) => (
            <UploadLogRow key={log.id} log={log} />
          ))}
          {uploadLogs.length === 0 && <div className="p-6 text-center text-sm text-muted-foreground">{t("admin.ops.emptyLogs")}</div>}
        </div>
      </div>
    </section>
  );
}
