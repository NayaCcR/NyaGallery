import type { SecurityLimitOverride, TranscodeJob, UploadHistoryItem, UploadLogItem } from "@/lib/types";

const MIB = 1024 * 1024;

export type AdminTranslate = (key: string, params?: Record<string, string | number>) => string;

export function formatBytes(value: number | null | undefined): string {
  if (!value) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index++;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function isTerminalTranscodeJob(job: TranscodeJob): boolean {
  const status = job.status.toLowerCase();
  return status === "success" || status === "error" || job.stage === "done" || job.progress >= 100;
}

export function terminalStatus(job: TranscodeJob): string {
  const status = job.status.toLowerCase();
  if (status === "error") return "error";
  if (status === "success" || job.stage === "done" || job.progress >= 100) return "success";
  return status;
}

/** Backend log messages are plain English; look them up per source and fall back to the raw text. */
export function localizedSyncMessage(namespace: string, message: string, t: AdminTranslate): string {
  const key = `admin.${namespace}.${message}`;
  const label = t(key);
  if (label !== key) return label;
  return message || "-";
}

export function localizedPixivMessage(message: string, t: AdminTranslate): string {
  return localizedSyncMessage("pixivMessages", message, t);
}

export function pixivStageLabel(stage: string | null, t: AdminTranslate): string {
  const value = stage || "waiting";
  const key = `admin.pixivStages.${value}`;
  const label = t(key);
  if (label !== key) return label;
  return stage || t("admin.pixivStages.waiting");
}

export function extraString(extra: Record<string, unknown>, key: string): string | null {
  const value = extra[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function extraNumber(extra: Record<string, unknown>, key: string): number | null {
  const value = extra[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function statusClass(status: string): string {
  if (status === "success") return "text-emerald-600 dark:text-emerald-400";
  if (status === "error") return "text-destructive";
  if (status === "running") return "text-primary";
  return "text-muted-foreground";
}

export function statusPillClass(status: string): string {
  if (status === "success") return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  if (status === "error") return "bg-destructive/10 text-destructive";
  if (status === "running") return "bg-primary/10 text-primary";
  if (status === "queued") return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
  return "bg-muted text-muted-foreground";
}

export function httpStatusClass(status: number): string {
  if (status >= 500) return "text-destructive";
  if (status >= 400) return "text-amber-600 dark:text-amber-400";
  if (status >= 200 && status < 300) return "text-emerald-600 dark:text-emerald-400";
  return "text-muted-foreground";
}

export function cacheStatusOfLog(log: UploadLogItem): string {
  const fromLog = log.cache_status;
  const fromExtra = typeof log.extra.cache_status === "string" ? log.extra.cache_status : null;
  return fromLog || fromExtra || "missing";
}

export function statusLabel(status: string, t: AdminTranslate): string {
  const key = `admin.logs.statuses.${status}`;
  const label = t(key);
  return label === key ? status : label;
}

export function logEventLabel(event: string, t: AdminTranslate): string {
  const key = `admin.logs.events.${event}`;
  const label = t(key);
  return label === key ? event : label;
}

export function formatLogEvent(log: UploadLogItem, t: AdminTranslate): string {
  return t("admin.logs.eventStatus", {
    event: logEventLabel(log.event, t),
    status: statusLabel(log.status, t),
  });
}

export function localizedMessage(message: string | null | undefined, t: AdminTranslate): string {
  const text = (message || "").trim();
  if (!text) return "";
  const requested = text.match(/^requested by (.+)$/i);
  if (requested) return t("admin.logs.messages.requestedBy", { username: requested[1] });
  const key = `admin.logs.messages.${text}`;
  const label = t(key);
  return label === key ? text : label;
}

export function cacheStatusLabel(status: string, t: AdminTranslate): string {
  if (status === "ready") return t("admin.cache.statusReady");
  if (status === "partial") return t("admin.cache.statusPartial");
  if (status === "queued") return t("admin.cache.statusQueued");
  return t("admin.cache.statusMissing");
}

export function cacheStatusClass(status: string): string {
  if (status === "ready") return "text-emerald-600 dark:text-emerald-400";
  if (status === "partial" || status === "queued") return "text-primary";
  return "text-amber-600 dark:text-amber-400";
}

export function cacheStatusPillClass(status: string): string {
  if (status === "ready") return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  if (status === "partial" || status === "queued") return "bg-primary/10 text-primary";
  return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
}

export function cacheDetail(item: UploadHistoryItem, t: AdminTranslate): string {
  if (item.cache_status === "ready") return t("admin.cache.previewThumbCached");
  const missing = [];
  if (!item.has_preview_cache) missing.push(t("admin.cache.preview"));
  if (!item.has_thumb_cache) missing.push(t("admin.cache.thumb"));
  const fallback = item.has_preview_cache ? t("admin.cache.previewCached") : t("admin.cache.fallbackOriginal");
  return t("admin.cache.detailMissing", {
    missing: missing.join(" + ") || t("admin.cache.missingCache"),
    fallback,
  });
}

export function stageLabel(stage: string, t: AdminTranslate): string {
  const value = stage || "unknown";
  const key = `admin.transcode.stages.${value}`;
  const label = t(key);
  if (label !== key) return label;
  return localizedMessage(value, t) || t("admin.transcode.stages.unknown");
}

export function stageDetail(job: TranscodeJob, t: AdminTranslate): string {
  if (job.stage === "encoding_webp") {
    return t("admin.transcode.stageDetails.encoding_webp");
  }
  if (job.stage === "encoding_thumb") return t("admin.transcode.stageDetails.encoding_thumb");
  if (job.stage === "reading_frames") return t("admin.transcode.stageDetails.reading_frames");
  if (job.stage === "encoding_preview") return t("admin.transcode.stageDetails.encoding_preview");
  return localizedMessage(job.message, t) || t("admin.transcode.stageDetails.waiting");
}

export function elapsedSeconds(value: string | null | undefined): number | null {
  return elapsedSecondsBetween(value);
}

export function elapsedSecondsBetween(value: string | null | undefined, endValue?: string | null): number | null {
  if (!value) return null;
  const start = new Date(value).getTime();
  if (Number.isNaN(start)) return null;
  const end = endValue ? new Date(endValue).getTime() : Date.now();
  if (Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
}

export function estimateRemainingSeconds(job: TranscodeJob): number | null {
  if (isTerminalTranscodeJob(job)) return null;
  const elapsed = elapsedSeconds(job.started_at);
  const progress = Math.max(0, Math.min(99.5, job.progress || 0));
  if (!elapsed || progress <= 0 || job.status !== "running") return null;
  return Math.max(0, elapsed * (100 - progress) / progress);
}

export function formatDuration(value: number | null | undefined): string {
  if (value == null) return "-";
  const total = Math.max(0, Math.round(value));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes <= 0) return `${seconds}s`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return hours > 0 ? `${hours}h ${mins}m ${seconds}s` : `${mins}m ${seconds}s`;
}

export function bytesToMiB(value: number): number {
  return Math.round((value || 0) / MIB);
}

export function limitValue(
  limits: Record<string, SecurityLimitOverride>,
  target: string,
  field: keyof SecurityLimitOverride
): number {
  return Number(limits[target]?.[field] ?? 0);
}

export function parseLines(value: string): string[] {
  return Array.from(new Set(value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)));
}
