"use client";

import type { Dispatch, SetStateAction } from "react";
import { BadgeDollarSign, KeyRound, LogIn, Save } from "lucide-react";
import { FanboxLogRow } from "@/components/admin/admin-operation-rows";
import {
  SavedCredentialList,
  SegmentedControl,
  StorageStrategySelect,
  SyncCard,
  SyncFieldGroup,
  SyncLogsSection,
  SyncNotice,
  SyncNumberField,
  SyncPanelLayout,
  SyncSubmitButton,
  SyncSwitchGroup,
} from "@/components/admin/admin-sync-shared";
import type { SyncBulkAction } from "@/components/admin/admin-sync-log-list";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SwitchLabel } from "@/components/ui/switch-label";
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
  onBulkAction: (action: SyncBulkAction, assetKeys: string[]) => unknown;
  onRetryFailed?: (targets: string[]) => unknown;
};

export function AdminFanboxPanel(props: AdminFanboxPanelProps) {
  const { t } = useI18n();
  const { busy, config, mode, onModeChange, target, onTargetChange, targets, onTargetsChange, savedSessions, savedSessionId, onSavedSessionIdChange, logs, dryRun } = props;
  const hasSession = Boolean(savedSessionId || props.sessionDraft.trim() || config?.session_configured);
  const canSubmit = mode === "creator" ? Boolean(target.trim()) : Boolean(targets.trim());

  return (
    <SyncPanelLayout
      main={
        <SyncCard icon={BadgeDollarSign} title={t("admin.fanbox.syncTitle")} description={t("admin.fanbox.syncDescription")}>
          <SegmentedControl
            value={mode}
            onChange={onModeChange}
            options={(["creator", "posts"] as FanboxSyncMode[]).map((value) => ({ value, label: t(`admin.fanbox.mode.${value}`) }))}
          />

          <SyncFieldGroup>
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
          </SyncFieldGroup>

          <SyncFieldGroup>
            <div className="grid gap-3 md:grid-cols-3">
              {mode === "creator" && (
                <>
                  <SyncNumberField label={t("admin.fanbox.limit")} value={props.limit} min={1} allowEmpty onChange={props.onLimitChange} hint={t("admin.fanbox.limitHint")} />
                  <SyncNumberField label={t("admin.fanbox.pageSize")} value={props.pageSize} min={1} max={300} onChange={(v) => props.onPageSizeChange(typeof v === "number" ? v : 10)} hint={t("admin.fanbox.pageSizeHint")} />
                  <SyncNumberField label={t("admin.fanbox.maxPages")} value={props.maxPages} min={1} allowEmpty onChange={props.onMaxPagesChange} hint={t("admin.fanbox.maxPagesHint")} />
                </>
              )}
              <SyncNumberField label={t("admin.fanbox.delay")} value={props.delay} min={0} step={0.5} suffix="s" onChange={(v) => props.onDelayChange(typeof v === "number" ? v : 1)} />
              <SyncNumberField label={t("admin.fanbox.downloadConcurrency")} value={props.downloadConcurrency} min={1} max={16} onChange={(v) => props.onDownloadConcurrencyChange(typeof v === "number" ? v : 3)} />
              <StorageStrategySelect label={t("admin.fanbox.storageStrategy")} value={props.storageStrategy} strategies={config?.storage_strategies} onChange={props.onStorageStrategyChange} />
            </div>
          </SyncFieldGroup>

          <SyncSwitchGroup>
            <SwitchLabel label={t("admin.fanbox.downloadMedia")} checked={props.downloadMedia} onChange={props.onDownloadMediaChange} />
            <SwitchLabel label={t("admin.fanbox.downloadFiles")} checked={props.downloadFiles} onChange={props.onDownloadFilesChange} />
            {mode === "creator" && <SwitchLabel label={t("admin.fanbox.backfill")} checked={props.backfill} onChange={props.onBackfillChange} />}
            <SwitchLabel label={t("admin.fanbox.rebuildDb")} checked={props.rebuildDb} onChange={props.onRebuildDbChange} />
            <SwitchLabel label={t("admin.fanbox.generateCache")} checked={props.generateCache} onChange={props.onGenerateCacheChange} />
            <SwitchLabel label={t("admin.fanbox.dryRun")} checked={dryRun} onChange={props.onDryRunChange} />
          </SyncSwitchGroup>

          {!hasSession && <SyncNotice>{t("admin.fanbox.sessionRequired")}</SyncNotice>}

          <SyncSubmitButton
            busy={busy === "fanbox"}
            disabled={!canSubmit}
            dryRun={dryRun}
            label={t("admin.fanbox.startSync")}
            dryRunLabel={t("admin.fanbox.startDryRun")}
            onClick={props.onSync}
          />
          <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.fanbox.note")}</p>
        </SyncCard>
      }
      side={
        <SyncCard icon={KeyRound} title={t("admin.fanbox.sessionsTitle")} description={t("admin.fanbox.sessionsDescription")}>
          <SavedCredentialList
            ns="admin.fanbox"
            selectLabel={t("admin.fanbox.useSavedSession")}
            noneLabel={t("admin.fanbox.noSavedSession")}
            emptyLabel={t("admin.fanbox.emptySessions")}
            labelPlaceholder={t("admin.fanbox.sessionLabel")}
            busyPrefix={{ label: "fanbox-session-label-", revoke: "fanbox-session-revoke-" }}
            busy={busy}
            items={savedSessions.map((item) => ({
              id: item.id,
              title: sessionTitle(item),
              meta: t(`admin.fanbox.sources.${item.source}`),
              isActive: item.is_active,
              label: item.label,
              lastUsedAt: item.last_used_at,
            }))}
            selectedId={savedSessionId}
            onSelect={onSavedSessionIdChange}
            labelDrafts={props.sessionLabelDrafts}
            onLabelDraftChange={(id, value) => props.onSessionLabelDraftsChange((current) => ({ ...current, [id]: value }))}
            onUpdateLabel={props.onUpdateSessionLabel}
            onRevoke={props.onRevokeSession}
          />
          <div className="space-y-1.5 rounded-md border border-border bg-muted/35 p-3">
            <Label>{t("admin.fanbox.loginTitle")}</Label>
            <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.fanbox.loginHint")}</p>
            <Input
              type="password"
              value={props.pixivCookieDraft}
              placeholder={t("admin.fanbox.pixivCookiePlaceholder")}
              onChange={(event) => props.onPixivCookieDraftChange(event.target.value)}
            />
            <Button variant="outline" size="sm" disabled={busy === "fanbox-login"} onClick={props.onLoginWithPixivCookie} className="w-full">
              <LogIn className="h-4 w-4" /> {t("admin.fanbox.loginAction")}
            </Button>
          </div>
          <div className="space-y-1.5 border-t border-border pt-3">
            <Label>{t("admin.fanbox.newSession")}</Label>
            <Input
              type="password"
              value={props.sessionDraft}
              placeholder={config?.session_configured ? t("admin.fanbox.sessionFromConfig") : "FANBOXSESSID"}
              onChange={(event) => props.onSessionDraftChange(event.target.value)}
            />
            <Input value={props.sessionLabel} placeholder={t("admin.fanbox.sessionLabel")} onChange={(event) => props.onSessionLabelChange(event.target.value)} />
            <Button variant="outline" size="sm" disabled={busy === "fanbox-session-save" || !props.sessionDraft.trim()} onClick={props.onSaveSession} className="w-full">
              <Save className="h-4 w-4" /> {t("admin.fanbox.saveSession")}
            </Button>
          </div>
        </SyncCard>
      }
      logs={
        <SyncLogsSection
          ns="admin.fanbox"
          logs={logs}
          pollingMode={props.pollingMode}
          lastUpdatedAt={props.lastUpdatedAt}
          refreshing={busy === "fanbox-log-refresh"}
          onRefresh={props.onRefreshLogs}
          bulkBusy={busy === "sync-bulk"}
          onBulkAction={props.onBulkAction}
          renderRow={(log) => (
            <FanboxLogRow log={log} onRetry={props.onRetryFailed ? (retryTargets) => { void props.onRetryFailed?.(retryTargets); } : undefined} />
          )}
        />
      }
    />
  );
}

function sessionTitle(item: FanboxSessionSummary): string {
  const account = item.fanbox_creator_id ? `@${item.fanbox_creator_id}` : item.fanbox_name || "";
  const masked = `${item.session_prefix}…${item.session_suffix}`;
  return [item.label, account, masked].filter(Boolean).join(" · ");
}