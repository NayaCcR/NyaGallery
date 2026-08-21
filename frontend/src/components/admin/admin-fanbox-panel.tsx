"use client";

import type { Dispatch, SetStateAction } from "react";
import { BadgeDollarSign, KeyRound, ListChecks, LogIn, RefreshCw, Save, ShieldAlert, Trash2 } from "lucide-react";
import { EmptyLine } from "@/components/admin/admin-fields";
import { formatDate } from "@/components/admin/admin-format";
import { FanboxLogRow } from "@/components/admin/admin-operation-rows";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SwitchLabel } from "@/components/ui/switch-label";
import { cn } from "@/lib/utils";
import type { AdminPollingMode } from "@/hooks/admin/use-admin-operations";
import type { FanboxSyncMode } from "@/hooks/admin/use-admin-fanbox";
import type { FanboxConfigResponse, FanboxSessionSummary, UploadLogItem } from "@/lib/types";

type AdminFanboxPanelProps = {
  busy: string | null;
  config: FanboxConfigResponse | null;
  mode: FanboxSyncMode;
  onModeChange: (value: FanboxSyncMode) => void;
  target: string;
  onTargetChange: (value: string) => void;
  targets: string;
  onTargetsChange: (value: string) => void;
  limit: number | "";
  onLimitChange: (value: number | "") => void;
  pageSize: number;
  onPageSizeChange: (value: number) => void;
  maxPages: number | "";
  onMaxPagesChange: (value: number | "") => void;
  delay: number;
  onDelayChange: (value: number) => void;
  downloadConcurrency: number;
  onDownloadConcurrencyChange: (value: number) => void;
  storageStrategy: string;
  onStorageStrategyChange: (value: string) => void;
  backfill: boolean;
  onBackfillChange: (value: boolean) => void;
  downloadMedia: boolean;
  onDownloadMediaChange: (value: boolean) => void;
  downloadFiles: boolean;
  onDownloadFilesChange: (value: boolean) => void;
  rebuildDb: boolean;
  onRebuildDbChange: (value: boolean) => void;
  generateCache: boolean;
  onGenerateCacheChange: (value: boolean) => void;
  dryRun: boolean;
  onDryRunChange: (value: boolean) => void;
  sessionDraft: string;
  onSessionDraftChange: (value: string) => void;
  sessionLabel: string;
  onSessionLabelChange: (value: string) => void;
  savedSessionId: number | null;
  onSavedSessionIdChange: (value: number | null) => void;
  savedSessions: FanboxSessionSummary[];
  sessionLabelDrafts: Record<number, string>;
  onSessionLabelDraftsChange: Dispatch<SetStateAction<Record<number, string>>>;
  pixivCookieDraft: string;
  onPixivCookieDraftChange: (value: string) => void;
  onSaveSession: () => unknown;
  onLoginWithPixivCookie: () => unknown;
  onUpdateSessionLabel: (sessionId: number) => unknown;
  onRevokeSession: (sessionId: number) => unknown;
  onSync: () => unknown;
  logs: UploadLogItem[];
  pollingMode: AdminPollingMode;
  lastUpdatedAt: string | null;
  onRefreshLogs: () => unknown;
  onRetryFailed?: (targets: string[]) => unknown;
};

export function AdminFanboxPanel(props: AdminFanboxPanelProps) {
  const { t } = useI18n();
  const {
    busy, config, mode, onModeChange, target, onTargetChange, targets, onTargetsChange,
    savedSessions, savedSessionId, onSavedSessionIdChange, logs, pollingMode, lastUpdatedAt,
    onRefreshLogs, onSync, dryRun,
  } = props;
  const activeSessions = savedSessions.filter((item) => item.is_active);
  const hasSession = Boolean(savedSessionId || props.sessionDraft.trim() || config?.session_configured);
  const canSubmit = mode === "creator" ? Boolean(target.trim()) : Boolean(targets.trim());

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <BadgeDollarSign className="h-4 w-4" /> {t("admin.fanbox.syncTitle")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("admin.fanbox.syncDescription")}</p>
        </div>

        <div className="flex gap-2">
          {(["creator", "posts"] as FanboxSyncMode[]).map((value) => (
            <Button key={value} variant={mode === value ? "default" : "outline"} size="sm" onClick={() => onModeChange(value)}>
              {t(`admin.fanbox.mode.${value}`)}
            </Button>
          ))}
        </div>

        {mode === "creator" ? (
          <div className="space-y-1.5">
            <Label>{t("admin.fanbox.creator")}</Label>
            <Input value={target} placeholder="nekoworks" onChange={(event) => onTargetChange(event.target.value)} />
            <p className="text-[11px] text-muted-foreground">{t("admin.fanbox.creatorHint")}</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label>{t("admin.fanbox.targets")}</Label>
            <textarea
              className="flex min-h-[110px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-ring"
              value={targets}
              placeholder={"https://nekoworks.fanbox.cc/posts/9261015\nhttps://nekoworks.fanbox.cc/posts/8265882"}
              onChange={(event) => onTargetsChange(event.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">{t("admin.fanbox.targetsHint")}</p>
          </div>
        )}

        {mode === "creator" && (
          <div className="grid gap-3 md:grid-cols-3">
            <NumberField label={t("admin.fanbox.limit")} value={props.limit} min={1} allowEmpty onChange={props.onLimitChange} hint={t("admin.fanbox.limitHint")} />
            <NumberField label={t("admin.fanbox.pageSize")} value={props.pageSize} min={1} max={300} onChange={(v) => props.onPageSizeChange(typeof v === "number" ? v : 10)} hint={t("admin.fanbox.pageSizeHint")} />
            <NumberField label={t("admin.fanbox.maxPages")} value={props.maxPages} min={1} allowEmpty onChange={props.onMaxPagesChange} hint={t("admin.fanbox.maxPagesHint")} />
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-3">
          <NumberField label={t("admin.fanbox.delay")} value={props.delay} min={0} step={0.5} onChange={(v) => props.onDelayChange(typeof v === "number" ? v : 1)} />
          <NumberField label={t("admin.fanbox.downloadConcurrency")} value={props.downloadConcurrency} min={1} max={16} onChange={(v) => props.onDownloadConcurrencyChange(typeof v === "number" ? v : 3)} />
          <div className="space-y-1.5">
            <Label>{t("admin.fanbox.storageStrategy")}</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
              value={props.storageStrategy}
              onChange={(event) => props.onStorageStrategyChange(event.target.value)}
            >
              {(config?.storage_strategies ?? []).map((strategy) => (
                <option key={strategy.name} value={strategy.name}>
                  {strategy.name}{strategy.is_default ? ` (${t("common.defaultOption")})` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-2 rounded-md border border-border bg-muted/35 p-3">
          <SwitchLabel label={t("admin.fanbox.downloadMedia")} checked={props.downloadMedia} onChange={props.onDownloadMediaChange} />
          <SwitchLabel label={t("admin.fanbox.downloadFiles")} checked={props.downloadFiles} onChange={props.onDownloadFilesChange} />
          {mode === "creator" && (
            <SwitchLabel label={t("admin.fanbox.backfill")} checked={props.backfill} onChange={props.onBackfillChange} />
          )}
          <SwitchLabel label={t("admin.fanbox.rebuildDb")} checked={props.rebuildDb} onChange={props.onRebuildDbChange} />
          <SwitchLabel label={t("admin.fanbox.generateCache")} checked={props.generateCache} onChange={props.onGenerateCacheChange} />
          <SwitchLabel label={t("admin.fanbox.dryRun")} checked={dryRun} onChange={props.onDryRunChange} />
        </div>

        {!hasSession && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <span>{t("admin.fanbox.sessionRequired")}</span>
          </div>
        )}

        <Button disabled={busy === "fanbox" || !canSubmit} onClick={onSync} className="w-full">
          <RefreshCw className="h-4 w-4" /> {dryRun ? t("admin.fanbox.startDryRun") : t("admin.fanbox.startSync")}
        </Button>

        <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.fanbox.note")}</p>
      </section>

      <aside className="space-y-6">
        <section className="space-y-3 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <KeyRound className="h-4 w-4" /> {t("admin.fanbox.sessionsTitle")}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">{t("admin.fanbox.sessionsDescription")}</p>
          </div>

          <div className="space-y-1.5 rounded-md border border-border bg-muted/35 p-3">
            <Label>{t("admin.fanbox.loginTitle")}</Label>
            <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.fanbox.loginHint")}</p>
            <Input
              type="password"
              value={props.pixivCookieDraft}
              placeholder={t("admin.fanbox.pixivCookiePlaceholder")}
              onChange={(event) => props.onPixivCookieDraftChange(event.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={busy === "fanbox-login"}
              onClick={props.onLoginWithPixivCookie}
              className="w-full"
            >
              <LogIn className="h-4 w-4" /> {t("admin.fanbox.loginAction")}
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label>{t("admin.fanbox.useSavedSession")}</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
              value={savedSessionId ? String(savedSessionId) : ""}
              onChange={(event) => onSavedSessionIdChange(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">{t("admin.fanbox.noSavedSession")}</option>
              {activeSessions.map((item) => (
                <option key={item.id} value={String(item.id)}>{sessionTitle(item)}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label>{t("admin.fanbox.newSession")}</Label>
            <Input
              type="password"
              value={props.sessionDraft}
              placeholder={config?.session_configured ? t("admin.fanbox.sessionFromConfig") : "FANBOXSESSID"}
              onChange={(event) => props.onSessionDraftChange(event.target.value)}
            />
            <Input value={props.sessionLabel} placeholder={t("admin.fanbox.sessionLabel")} onChange={(event) => props.onSessionLabelChange(event.target.value)} />
            <Button
              variant="outline"
              size="sm"
              disabled={busy === "fanbox-session-save" || !props.sessionDraft.trim()}
              onClick={props.onSaveSession}
              className="w-full"
            >
              <Save className="h-4 w-4" /> {t("admin.fanbox.saveSession")}
            </Button>
          </div>

          <div className="space-y-2">
            {savedSessions.length === 0 && <EmptyLine text={t("admin.fanbox.emptySessions")} />}
            {savedSessions.map((item) => (
              <div key={item.id} className={cn("space-y-2 rounded-md border border-border p-3 text-xs", !item.is_active && "opacity-60")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate font-medium" title={sessionTitle(item)}>{sessionTitle(item)}</span>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {item.is_active ? t(`admin.fanbox.sources.${item.source}`) : t("admin.fanbox.revoked")}
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {item.last_used_at ? t("admin.fanbox.lastUsed", { at: formatDate(item.last_used_at) }) : t("admin.fanbox.neverUsed")}
                </div>
                {item.is_active && (
                  <div className="flex gap-2">
                    <Input
                      value={props.sessionLabelDrafts[item.id] ?? item.label}
                      placeholder={t("admin.fanbox.sessionLabel")}
                      onChange={(event) =>
                        props.onSessionLabelDraftsChange((current) => ({ ...current, [item.id]: event.target.value }))
                      }
                    />
                    <Button variant="outline" size="sm" disabled={busy === `fanbox-session-label-${item.id}`} onClick={() => props.onUpdateSessionLabel(item.id)}>
                      <Save className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" disabled={busy === `fanbox-session-revoke-${item.id}`} onClick={() => props.onRevokeSession(item.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-medium">
                <ListChecks className="h-4 w-4" /> {t("admin.fanbox.logsTitle")}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {pollingMode === "active" && t("admin.fanbox.pollingActive")}
                {pollingMode === "idle" && t("admin.fanbox.pollingIdle")}
                {pollingMode === "paused" && t("admin.fanbox.pollingPaused")}
                {lastUpdatedAt && ` · ${formatDate(lastUpdatedAt)}`}
              </p>
            </div>
            <Button variant="outline" size="sm" disabled={busy === "fanbox-log-refresh"} onClick={onRefreshLogs}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          <div className="max-h-[520px] space-y-2 overflow-auto">
            {logs.map((log) => (
              <FanboxLogRow
                key={log.id}
                log={log}
                onRetry={props.onRetryFailed ? (targets) => { props.onRetryFailed?.(targets); } : undefined}
              />
            ))}
            {logs.length === 0 && <EmptyLine text={t("admin.fanbox.emptyLogs")} />}
          </div>
        </section>
      </aside>
    </div>
  );
}

function NumberField({
  label, value, onChange, min, max, step, allowEmpty = false, hint,
}: {
  label: string;
  value: number | "";
  onChange: (value: number | "") => void;
  min?: number;
  max?: number;
  step?: number;
  allowEmpty?: boolean;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value === "" ? "" : String(value)}
        onChange={(event) => {
          const raw = event.target.value;
          if (raw === "" && allowEmpty) {
            onChange("");
            return;
          }
          const parsed = Number(raw);
          if (!Number.isFinite(parsed)) return;
          onChange(Math.min(max ?? Number.MAX_SAFE_INTEGER, Math.max(min ?? 0, parsed)));
        }}
      />
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function sessionTitle(item: FanboxSessionSummary): string {
  const account = item.fanbox_creator_id ? `@${item.fanbox_creator_id}` : item.fanbox_name || "";
  const masked = `${item.session_prefix}…${item.session_suffix}`;
  return [item.label, account, masked].filter(Boolean).join(" · ");
}
