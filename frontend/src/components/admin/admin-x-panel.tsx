"use client";

import type { Dispatch, SetStateAction } from "react";
import { Hash, KeyRound, Save } from "lucide-react";
import { XLogRow } from "@/components/admin/admin-operation-rows";
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
import type { XSyncMode } from "@/hooks/admin/use-admin-x";
import type { UploadLogItem, XConfigResponse, XTokenSummary } from "@/lib/types";

type AdminXPanelProps = {
  busy: string | null;
  config: XConfigResponse | null;
  mode: XSyncMode;
  onModeChange: (value: XSyncMode) => void;
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
  includeReplies: boolean;
  onIncludeRepliesChange: (value: boolean) => void;
  mediaOnly: boolean;
  onMediaOnlyChange: (value: boolean) => void;
  backfill: boolean;
  onBackfillChange: (value: boolean) => void;
  downloadMedia: boolean;
  onDownloadMediaChange: (value: boolean) => void;
  rebuildDb: boolean;
  onRebuildDbChange: (value: boolean) => void;
  generateCache: boolean;
  onGenerateCacheChange: (value: boolean) => void;
  makePublic: boolean;
  onMakePublicChange: (value: boolean) => void;
  dryRun: boolean;
  onDryRunChange: (value: boolean) => void;
  tokenDraft: string;
  onTokenDraftChange: (value: string) => void;
  ct0Draft: string;
  onCt0DraftChange: (value: string) => void;
  tokenLabel: string;
  onTokenLabelChange: (value: string) => void;
  savedTokenId: number | null;
  onSavedTokenIdChange: (value: number | null) => void;
  savedTokens: XTokenSummary[];
  tokenLabelDrafts: Record<number, string>;
  onTokenLabelDraftsChange: Dispatch<SetStateAction<Record<number, string>>>;
  onSaveToken: () => unknown;
  onUpdateTokenLabel: (tokenId: number) => unknown;
  onRevokeToken: (tokenId: number) => unknown;
  onSync: () => unknown;
  logs: UploadLogItem[];
  pollingMode: AdminPollingMode;
  lastUpdatedAt: string | null;
  onRefreshLogs: () => unknown;
  onBulkAction: (action: SyncBulkAction, assetKeys: string[]) => unknown;
  onRetryFailed?: (targets: string[]) => unknown;
};

export function AdminXPanel(props: AdminXPanelProps) {
  const { t } = useI18n();
  const { busy, config, mode, onModeChange, target, onTargetChange, targets, onTargetsChange, savedTokens, savedTokenId, onSavedTokenIdChange, logs, onRetryFailed, dryRun } = props;
  const hasSession = Boolean(savedTokenId || (props.tokenDraft.trim() && props.ct0Draft.trim()) || config?.session_configured);
  const canSubmit = mode === "user" ? Boolean(target.trim()) && hasSession : Boolean(targets.trim());

  return (
    <SyncPanelLayout
      main={
        <SyncCard icon={Hash} title={t("admin.x.syncTitle")} description={t("admin.x.syncDescription")}>
          <SegmentedControl
            value={mode}
            onChange={onModeChange}
            options={(["posts", "user"] as XSyncMode[]).map((value) => ({ value, label: t(`admin.x.mode.${value}`) }))}
          />

          <SyncFieldGroup>
            {mode === "posts" ? (
              <div className="space-y-1.5">
                <Label>{t("admin.x.targets")}</Label>
                <textarea
                  className="flex min-h-[110px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-ring"
                  value={targets}
                  placeholder={"https://x.com/user/status/1234567890\nhttps://x.com/user/status/1234567891"}
                  onChange={(event) => onTargetsChange(event.target.value)}
                />
                <p className="text-[11px] text-muted-foreground">{t("admin.x.targetsHint")}</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label>{t("admin.x.username")}</Label>
                <Input value={target} placeholder="NyaGallery" onChange={(event) => onTargetChange(event.target.value)} />
                <p className="text-[11px] text-muted-foreground">{t("admin.x.usernameHint")}</p>
              </div>
            )}
          </SyncFieldGroup>

          <SyncFieldGroup>
            <div className="grid gap-3 md:grid-cols-3">
              {mode === "user" && (
                <>
                  <SyncNumberField label={t("admin.x.limit")} value={props.limit} min={1} allowEmpty onChange={props.onLimitChange} hint={t("admin.x.limitHint")} />
                  <SyncNumberField label={t("admin.x.pageSize")} value={props.pageSize} min={1} max={100} onChange={(value) => props.onPageSizeChange(typeof value === "number" ? value : 20)} hint={t("admin.x.pageSizeHint")} />
                  <SyncNumberField label={t("admin.x.maxPages")} value={props.maxPages} min={1} allowEmpty onChange={props.onMaxPagesChange} hint={t("admin.x.maxPagesHint")} />
                </>
              )}
              <SyncNumberField label={t("admin.x.delay")} value={props.delay} min={0} step={0.5} suffix="s" onChange={(value) => props.onDelayChange(typeof value === "number" ? value : 2)} hint={t("admin.x.delayHint")} />
              <SyncNumberField label={t("admin.x.downloadConcurrency")} value={props.downloadConcurrency} min={1} max={16} onChange={(value) => props.onDownloadConcurrencyChange(typeof value === "number" ? value : 4)} />
              <StorageStrategySelect label={t("admin.x.storageStrategy")} value={props.storageStrategy} strategies={config?.storage_strategies} onChange={props.onStorageStrategyChange} />
            </div>
          </SyncFieldGroup>

          <SyncSwitchGroup>
            <SwitchLabel label={t("admin.x.downloadMedia")} checked={props.downloadMedia} onChange={props.onDownloadMediaChange} />
            {mode === "user" && (
              <>
                <SwitchLabel label={t("admin.x.mediaOnly")} checked={props.mediaOnly} onChange={props.onMediaOnlyChange} />
                <SwitchLabel label={t("admin.x.includeReplies")} checked={props.includeReplies} onChange={props.onIncludeRepliesChange} />
                <SwitchLabel label={t("admin.x.backfill")} checked={props.backfill} onChange={props.onBackfillChange} />
              </>
            )}
            <SwitchLabel label={t("admin.x.rebuildDb")} checked={props.rebuildDb} onChange={props.onRebuildDbChange} />
            <SwitchLabel label={t("admin.x.generateCache")} checked={props.generateCache} onChange={props.onGenerateCacheChange} />
            <SwitchLabel label={t("admin.x.makePublic")} checked={props.makePublic} onChange={props.onMakePublicChange} />
            <SwitchLabel label={t("admin.x.dryRun")} checked={dryRun} onChange={props.onDryRunChange} />
          </SyncSwitchGroup>

          {mode === "user" && !hasSession && <SyncNotice>{t("admin.x.sessionRequired")}</SyncNotice>}

          <SyncSubmitButton
            busy={busy === "x"}
            disabled={!canSubmit}
            dryRun={dryRun}
            label={t("admin.x.startSync")}
            dryRunLabel={t("admin.x.startDryRun")}
            onClick={props.onSync}
          />
          <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.x.note")}</p>
        </SyncCard>
      }
      side={
        <SyncCard icon={KeyRound} title={t("admin.x.tokensTitle")} description={t("admin.x.tokensDescription")}>
          <SavedCredentialList
            ns="admin.x"
            selectLabel={t("admin.x.useSavedToken")}
            noneLabel={t("admin.x.noSavedToken")}
            emptyLabel={t("admin.x.emptyTokens")}
            labelPlaceholder={t("admin.x.tokenLabel")}
            busyPrefix={{ label: "x-token-label-", revoke: "x-token-revoke-" }}
            busy={busy}
            items={savedTokens.map((token) => ({
              id: token.id,
              title: tokenTitle(token),
              meta: token.has_ct0 ? token.host : t("admin.x.missingCt0"),
              isActive: token.is_active,
              label: token.label,
              lastUsedAt: token.last_used_at,
            }))}
            selectedId={savedTokenId}
            onSelect={onSavedTokenIdChange}
            labelDrafts={props.tokenLabelDrafts}
            onLabelDraftChange={(id, value) => props.onTokenLabelDraftsChange((current) => ({ ...current, [id]: value }))}
            onUpdateLabel={props.onUpdateTokenLabel}
            onRevoke={props.onRevokeToken}
          />
          <div className="space-y-1.5 border-t border-border pt-3">
            <Label>{t("admin.x.newToken")}</Label>
            <Input
              type="password"
              value={props.tokenDraft}
              placeholder={config?.session_configured ? t("admin.x.tokenFromConfig") : "auth_token"}
              onChange={(event) => props.onTokenDraftChange(event.target.value)}
            />
            <Input type="password" value={props.ct0Draft} placeholder="ct0" onChange={(event) => props.onCt0DraftChange(event.target.value)} />
            <Input value={props.tokenLabel} placeholder={t("admin.x.tokenLabel")} onChange={(event) => props.onTokenLabelChange(event.target.value)} />
            <Button variant="outline" size="sm" disabled={busy === "x-token-save" || !props.tokenDraft.trim()} onClick={props.onSaveToken} className="w-full">
              <Save className="h-4 w-4" /> {t("admin.x.saveToken")}
            </Button>
            <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.x.tokenHelp")}</p>
          </div>
        </SyncCard>
      }
      logs={
        <SyncLogsSection
          ns="admin.x"
          logs={logs}
          pollingMode={props.pollingMode}
          lastUpdatedAt={props.lastUpdatedAt}
          refreshing={busy === "x-log-refresh"}
          onRefresh={props.onRefreshLogs}
          bulkBusy={busy === "sync-bulk"}
          onBulkAction={props.onBulkAction}
          renderRow={(log) => (
            <XLogRow log={log} onRetry={onRetryFailed ? (retryTargets) => { void onRetryFailed(retryTargets); } : undefined} />
          )}
        />
      }
    />
  );
}

function tokenTitle(token: XTokenSummary): string {
  const account = token.x_screen_name ? `@${token.x_screen_name}` : "";
  const masked = `${token.token_prefix}…${token.token_suffix}`;
  return [token.label, account, masked].filter(Boolean).join(" · ");
}