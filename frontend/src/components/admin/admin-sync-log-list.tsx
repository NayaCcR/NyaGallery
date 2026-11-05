"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, Eye, EyeOff, Lock, RotateCcw } from "lucide-react";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SyncLogAsset, UploadLogItem } from "@/lib/types";

export type SyncBulkAction = "public" | "private" | "retry";

/** Asset keys belonging to a sync log, in display order. */
function logAssetKeys(log: UploadLogItem): string[] {
  return (log.sync_assets ?? []).map((asset) => asset.asset_key);
}

/**
 * Wraps the per-platform log rows with selection, a transcode/cache progress line
 * and a collapsible per-asset list. Bulk actions apply to every asset of the selected logs.
 */
export function SyncLogList({
  logs,
  busy,
  onBulkAction,
  renderRow,
}: {
  logs: UploadLogItem[];
  busy: boolean;
  onBulkAction: (action: SyncBulkAction, assetKeys: string[]) => Promise<unknown> | unknown;
  renderRow: (log: UploadLogItem) => ReactNode;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const selectable = useMemo(() => logs.filter((log) => (log.sync_assets?.length ?? 0) > 0), [logs]);

  // Forget selections for logs that disappeared or lost their assets.
  useEffect(() => {
    setSelected((current) => {
      if (current.size === 0) return current;
      const ids = new Set(selectable.map((log) => log.id));
      const next = new Set(Array.from(current).filter((id) => ids.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [selectable]);

  const selectedLogs = selectable.filter((log) => selected.has(log.id));
  const selectedAssets = useMemo(
    () => Array.from(new Set(selectedLogs.flatMap(logAssetKeys))),
    [selectedLogs]
  );
  const failedSelected = selectedLogs.flatMap((log) => (log.sync_assets ?? []).filter((asset) => asset.transcode_status === "error")).length;
  const allSelected = selectable.length > 0 && selectedLogs.length === selectable.length;
  const someSelected = selectedLogs.length > 0 && !allSelected;

  const toggle = (id: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(selectable.map((log) => log.id)));

  async function apply(action: SyncBulkAction) {
    if (selectedAssets.length === 0) return;
    await Promise.resolve(onBulkAction(action, selectedAssets));
  }

  return (
    <div className="space-y-3">
      {selectable.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/25 px-3 py-2">
          <label className="inline-flex cursor-pointer select-none items-center gap-2 text-xs">
            <input
              type="checkbox"
              ref={(node) => {
                if (node) node.indeterminate = someSelected;
              }}
              checked={allSelected}
              onChange={toggleAll}
              className="h-4 w-4 cursor-pointer rounded border-border accent-primary"
            />
            {t("admin.syncLogs.selectAll")}
          </label>
          <span className="text-xs tabular-nums text-muted-foreground">
            {t("admin.syncLogs.selectedCount", { logs: selectedLogs.length, assets: selectedAssets.length })}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <Button type="button" size="sm" variant="outline" className="h-7 px-2.5 text-xs" disabled={busy || selectedAssets.length === 0} onClick={() => void apply("public")}>
              <Eye className="h-3.5 w-3.5" /> {t("admin.syncLogs.makePublic")}
            </Button>
            <Button type="button" size="sm" variant="outline" className="h-7 px-2.5 text-xs" disabled={busy || selectedAssets.length === 0} onClick={() => void apply("private")}>
              <EyeOff className="h-3.5 w-3.5" /> {t("admin.syncLogs.makePrivate")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant={failedSelected > 0 ? "default" : "outline"}
              className="h-7 px-2.5 text-xs"
              disabled={busy || failedSelected === 0}
              onClick={() => void apply("retry")}
            >
              <RotateCcw className={cn("h-3.5 w-3.5", busy && "animate-spin")} /> {t("admin.syncLogs.retryFailed")} ({failedSelected})
            </Button>
          </div>
        </div>
      )}
      <div className="grid gap-2 xl:grid-cols-2">
        {logs.map((log) => (
          <SyncLogItem
            key={log.id}
            log={log}
            selected={selected.has(log.id)}
            onToggle={() => toggle(log.id)}
          >
            {renderRow(log)}
          </SyncLogItem>
        ))}
      </div>
    </div>
  );
}

function SyncLogItem({ log, selected, onToggle, children }: { log: UploadLogItem; selected: boolean; onToggle: () => void; children: ReactNode }) {
  const { t } = useI18n();
  const assets = log.sync_assets ?? [];
  const summary = log.sync_assets_summary;
  const [expanded, setExpanded] = useState(false);
  const multi = assets.length > 1;

  return (
    <div className={cn("flex gap-2 rounded-lg transition-colors", selected && "bg-primary/5 ring-1 ring-primary/30")}>
      <div className="pl-2 pt-3">
        {assets.length > 0 ? (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={t("admin.syncLogs.selectLog", { id: log.id })}
            className="h-4 w-4 cursor-pointer rounded border-border accent-primary"
          />
        ) : (
          <span className="block h-4 w-4" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1.5 py-1 pr-1">
        {children}
        {summary && summary.total > 0 && (
          <div className="space-y-1.5 px-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
              <SyncProgress summary={summary} />
              <span className="text-muted-foreground tabular-nums">
                {t("admin.syncLogs.publicCount", { public: summary.public, total: summary.total })}
              </span>
              {summary.recovered && (
                <span className="text-muted-foreground/80" title={t("admin.syncLogs.recoveredHint")}>
                  {t("admin.syncLogs.recovered")}
                </span>
              )}
              {multi && (
                <button
                  type="button"
                  onClick={() => setExpanded((value) => !value)}
                  aria-expanded={expanded}
                  className="ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-muted-foreground hover:bg-muted hover:text-foreground focus-ring"
                >
                  {expanded ? t("admin.syncLogs.collapse") : t("admin.syncLogs.expand", { count: assets.length })}
                  <ChevronDown className={cn("h-3 w-3 transition-transform", expanded && "rotate-180")} />
                </button>
              )}
            </div>
            {!multi && assets[0] && <AssetLine asset={assets[0]} compact />}
            {multi && expanded && (
              <div className="max-h-64 space-y-1 overflow-auto rounded-md border border-border bg-background/60 p-1.5">
                {assets.map((asset) => <AssetLine key={asset.asset_key} asset={asset} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SyncProgress({ summary }: { summary: NonNullable<UploadLogItem["sync_assets_summary"]> }) {
  const { t } = useI18n();
  const failed = summary.failed > 0;
  const done = summary.cached >= summary.total;
  const percent = summary.total > 0 ? Math.round((summary.cached / summary.total) * 100) : 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-medium tabular-nums",
        failed ? "text-destructive" : done ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"
      )}
      title={failed ? t("admin.syncLogs.failedHint", { count: summary.failed }) : undefined}
    >
      <span className="relative h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full", failed ? "bg-destructive" : done ? "bg-emerald-500" : "bg-primary")}
          style={{ width: `${percent}%` }}
        />
      </span>
      {t("admin.syncLogs.transcodeProgress", { done: summary.cached, total: summary.total })}
      {failed && <span>· {t("admin.syncLogs.failedCount", { count: summary.failed })}</span>}
      {summary.pending > 0 && !failed && <span className="font-normal text-muted-foreground">· {t("admin.syncLogs.pendingCount", { count: summary.pending })}</span>}
    </span>
  );
}

function AssetLine({ asset, compact = false }: { asset: SyncLogAsset; compact?: boolean }) {
  const { t } = useI18n();
  const failed = asset.transcode_status === "error";
  const ready = asset.cache_status === "ready";
  const dot = failed ? "bg-destructive" : ready ? "bg-emerald-500" : asset.transcode_status === "running" || asset.transcode_status === "queued" ? "bg-primary animate-pulse" : "bg-muted-foreground/50";
  const statusText = failed
    ? t("admin.syncLogs.assetFailed")
    : ready
      ? t("admin.syncLogs.assetReady")
      : asset.transcode_status === "running" || asset.transcode_status === "queued"
        ? t("admin.syncLogs.assetPending")
        : t("admin.syncLogs.assetMissing");
  return (
    <div className={cn("flex items-center gap-2 rounded px-1.5 py-1 text-[11px]", !compact && "hover:bg-muted/60", failed && !compact && "bg-destructive/5")}>
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} />
      {asset.page_index != null && <span className="w-7 shrink-0 tabular-nums text-muted-foreground">p{asset.page_index}</span>}
      <Link href={`/asset/${encodeURIComponent(asset.asset_key)}`} className="min-w-0 flex-1 truncate font-mono hover:underline" title={asset.asset_key}>
        {asset.asset_key}
      </Link>
      <span className={cn("shrink-0", failed ? "text-destructive" : "text-muted-foreground")} title={asset.transcode_error ?? undefined}>
        {statusText}
      </span>
      <span className="inline-flex shrink-0 items-center gap-0.5 text-muted-foreground" title={asset.visibility === "public" ? t("admin.syncLogs.public") : t("admin.syncLogs.private")}>
        {asset.visibility === "public" ? <Eye className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
      </span>
    </div>
  );
}
