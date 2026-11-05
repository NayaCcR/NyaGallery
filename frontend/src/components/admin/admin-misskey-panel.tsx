"use client";

import type { Dispatch, SetStateAction } from "react";
import { AtSign, KeyRound, Save } from "lucide-react";
import { MisskeyLogRow } from "@/components/admin/admin-operation-rows";
import {
  SavedCredentialList,
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
import type { MisskeyConfigResponse, MisskeyTokenSummary, UploadLogItem } from "@/lib/types";

type AdminMisskeyPanelProps = {
  busy: string | null;
  config: MisskeyConfigResponse | null;
  target: string;
  onTargetChange: (value: string) => void;
  host: string;
  onHostChange: (value: string) => void;
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
  tokenLabel: string;
  onTokenLabelChange: (value: string) => void;
  savedTokenId: number | null;
  onSavedTokenIdChange: (value: number | null) => void;
  savedTokens: MisskeyTokenSummary[];
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
  onRetryMisskey: (target: string) => unknown;
};

export function AdminMisskeyPanel(props: AdminMisskeyPanelProps) {
  const { t } = useI18n();
  const { busy, config, target, onTargetChange, savedTokens, savedTokenId, onSavedTokenIdChange, logs, dryRun } = props;
  const hasCredential = Boolean(savedTokenId || props.tokenDraft.trim() || config?.token_configured);

  return (
    <SyncPanelLayout
      main={
        <SyncCard icon={AtSign} title={t("admin.misskey.syncTitle")} description={t("admin.misskey.syncDescription")}>
          <SyncFieldGroup>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <Label>{t("admin.misskey.username")}</Label>
                <Input value={target} placeholder="noa" onChange={(event) => onTargetChange(event.target.value)} />
                <p className="text-[11px] text-muted-foreground">{t("admin.misskey.usernameHint")}</p>
              </div>
              <div className="space-y-1.5">
                <Label>{t("admin.misskey.host")}</Label>
                <Input value={props.host} placeholder={config?.host || "misskey.io"} onChange={(event) => props.onHostChange(event.target.value)} />
                <p className="text-[11px] text-muted-foreground">{t("admin.misskey.hostHint")}</p>
              </div>
            </div>
          </SyncFieldGroup>

          <SyncFieldGroup>
            <div className="grid gap-3 md:grid-cols-3">
              <SyncNumberField label={t("admin.misskey.limit")} value={props.limit} min={1} allowEmpty onChange={props.onLimitChange} hint={t("admin.misskey.limitHint")} />
              <SyncNumberField label={t("admin.misskey.pageSize")} value={props.pageSize} min={1} max={100} onChange={(value) => props.onPageSizeChange(typeof value === "number" ? value : 100)} hint={t("admin.misskey.pageSizeHint")} />
              <SyncNumberField label={t("admin.misskey.maxPages")} value={props.maxPages} min={1} allowEmpty onChange={props.onMaxPagesChange} hint={t("admin.misskey.maxPagesHint")} />
              <SyncNumberField label={t("admin.misskey.delay")} value={props.delay} min={0} step={0.5} suffix="s" onChange={(value) => props.onDelayChange(typeof value === "number" ? value : 1)} />
              <SyncNumberField label={t("admin.misskey.downloadConcurrency")} value={props.downloadConcurrency} min={1} max={16} onChange={(value) => props.onDownloadConcurrencyChange(typeof value === "number" ? value : 5)} />
              <StorageStrategySelect label={t("admin.misskey.storageStrategy")} value={props.storageStrategy} strategies={config?.storage_strategies} onChange={props.onStorageStrategyChange} />
            </div>
          </SyncFieldGroup>

          <SyncSwitchGroup>
            <SwitchLabel label={t("admin.misskey.downloadMedia")} checked={props.downloadMedia} onChange={props.onDownloadMediaChange} />
            <SwitchLabel label={t("admin.misskey.includeReplies")} checked={props.includeReplies} onChange={props.onIncludeRepliesChange} />
            <SwitchLabel label={t("admin.misskey.backfill")} checked={props.backfill} onChange={props.onBackfillChange} />
            <SwitchLabel label={t("admin.misskey.rebuildDb")} checked={props.rebuildDb} onChange={props.onRebuildDbChange} />
            <SwitchLabel label={t("admin.misskey.generateCache")} checked={props.generateCache} onChange={props.onGenerateCacheChange} />
            <SwitchLabel label={t("admin.misskey.makePublic")} checked={props.makePublic} onChange={props.onMakePublicChange} />
            <SwitchLabel label={t("admin.misskey.dryRun")} checked={dryRun} onChange={props.onDryRunChange} />
          </SyncSwitchGroup>

          {!hasCredential && <SyncNotice>{t("admin.misskey.tokenMissing")}</SyncNotice>}

          <SyncSubmitButton
            busy={busy === "misskey"}
            disabled={!target.trim() || !hasCredential}
            dryRun={dryRun}
            label={t("admin.misskey.startSync")}
            dryRunLabel={t("admin.misskey.startDryRun")}
            onClick={props.onSync}
          />
          <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.misskey.note")}</p>
        </SyncCard>
      }
      side={
        <SyncCard icon={KeyRound} title={t("admin.misskey.tokensTitle")} description={t("admin.misskey.tokensDescription")}>
          <SavedCredentialList
            ns="admin.misskey"
            selectLabel={t("admin.misskey.useSavedToken")}
            noneLabel={t("admin.misskey.noSavedToken")}
            emptyLabel={t("admin.misskey.emptyTokens")}
            labelPlaceholder={t("admin.misskey.tokenLabel")}
            busyPrefix={{ label: "misskey-token-label-", revoke: "misskey-token-revoke-" }}
            busy={busy}
            items={savedTokens.map((token) => ({
              id: token.id,
              title: tokenTitle(token),
              meta: token.host,
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
            <Label>{t("admin.misskey.newToken")}</Label>
            <Input
              type="password"
              value={props.tokenDraft}
              placeholder={config?.token_configured ? t("admin.misskey.tokenFromConfig") : ""}
              onChange={(event) => props.onTokenDraftChange(event.target.value)}
            />
            <Input value={props.tokenLabel} placeholder={t("admin.misskey.tokenLabel")} onChange={(event) => props.onTokenLabelChange(event.target.value)} />
            <Button variant="outline" size="sm" disabled={busy === "misskey-token-save" || !props.tokenDraft.trim()} onClick={props.onSaveToken} className="w-full">
              <Save className="h-4 w-4" /> {t("admin.misskey.saveToken")}
            </Button>
          </div>
        </SyncCard>
      }
      logs={
        <SyncLogsSection
          ns="admin.misskey"
          logs={logs}
          pollingMode={props.pollingMode}
          lastUpdatedAt={props.lastUpdatedAt}
          refreshing={busy === "misskey-log-refresh"}
          onRefresh={props.onRefreshLogs}
          bulkBusy={busy === "sync-bulk"}
          onBulkAction={props.onBulkAction}
          renderRow={(log) => <MisskeyLogRow log={log} onRetry={props.onRetryMisskey} />}
        />
      }
    />
  );
}

function tokenTitle(token: MisskeyTokenSummary): string {
  const account = token.misskey_username ? `@${token.misskey_username}` : "";
  const masked = `${token.token_prefix}…${token.token_suffix}`;
  return [token.label, account, masked].filter(Boolean).join(" · ");
}