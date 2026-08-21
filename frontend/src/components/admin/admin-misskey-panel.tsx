"use client";

import type { Dispatch, SetStateAction } from "react";
import { AtSign, KeyRound, ListChecks, RefreshCw, Save, ShieldAlert, Trash2 } from "lucide-react";
import { EmptyLine } from "@/components/admin/admin-fields";
import { formatDate } from "@/components/admin/admin-format";
import { MisskeyLogRow } from "@/components/admin/admin-operation-rows";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SwitchLabel } from "@/components/ui/switch-label";
import { cn } from "@/lib/utils";
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
};

export function AdminMisskeyPanel(props: AdminMisskeyPanelProps) {
  const { t } = useI18n();
  const {
    busy,
    config,
    target,
    onTargetChange,
    savedTokens,
    savedTokenId,
    onSavedTokenIdChange,
    logs,
    pollingMode,
    lastUpdatedAt,
    onRefreshLogs,
    onSync,
    dryRun,
  } = props;
  const activeTokens = savedTokens.filter((token) => token.is_active);
  const hasCredential = Boolean(savedTokenId || props.tokenDraft.trim() || config?.token_configured);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <AtSign className="h-4 w-4" /> {t("admin.misskey.syncTitle")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("admin.misskey.syncDescription")}</p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>{t("admin.misskey.username")}</Label>
            <Input
              value={target}
              placeholder="noa"
              onChange={(event) => onTargetChange(event.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">{t("admin.misskey.usernameHint")}</p>
          </div>
          <div className="space-y-1.5">
            <Label>{t("admin.misskey.host")}</Label>
            <Input
              value={props.host}
              placeholder={config?.host || "misskey.io"}
              onChange={(event) => props.onHostChange(event.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">{t("admin.misskey.hostHint")}</p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <NumberField
            label={t("admin.misskey.limit")}
            value={props.limit}
            min={1}
            allowEmpty
            onChange={props.onLimitChange}
            hint={t("admin.misskey.limitHint")}
          />
          <NumberField
            label={t("admin.misskey.pageSize")}
            value={props.pageSize}
            min={1}
            max={100}
            onChange={(value) => props.onPageSizeChange(typeof value === "number" ? value : 100)}
            hint={t("admin.misskey.pageSizeHint")}
          />
          <NumberField
            label={t("admin.misskey.maxPages")}
            value={props.maxPages}
            min={1}
            allowEmpty
            onChange={props.onMaxPagesChange}
            hint={t("admin.misskey.maxPagesHint")}
          />
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <NumberField
            label={t("admin.misskey.delay")}
            value={props.delay}
            min={0}
            step={0.5}
            onChange={(value) => props.onDelayChange(typeof value === "number" ? value : 1)}
          />
          <NumberField
            label={t("admin.misskey.downloadConcurrency")}
            value={props.downloadConcurrency}
            min={1}
            max={16}
            onChange={(value) => props.onDownloadConcurrencyChange(typeof value === "number" ? value : 5)}
          />
          <div className="space-y-1.5">
            <Label>{t("admin.misskey.storageStrategy")}</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
              value={props.storageStrategy}
              onChange={(event) => props.onStorageStrategyChange(event.target.value)}
            >
              {(config?.storage_strategies ?? []).map((strategy) => (
                <option key={strategy.name} value={strategy.name}>
                  {strategy.name}
                  {strategy.is_default ? ` (${t("common.defaultOption")})` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-2 rounded-md border border-border bg-muted/35 p-3">
          <SwitchLabel label={t("admin.misskey.downloadMedia")} checked={props.downloadMedia} onChange={props.onDownloadMediaChange} />
          <SwitchLabel label={t("admin.misskey.includeReplies")} checked={props.includeReplies} onChange={props.onIncludeRepliesChange} />
          <SwitchLabel label={t("admin.misskey.backfill")} checked={props.backfill} onChange={props.onBackfillChange} />
          <SwitchLabel label={t("admin.misskey.rebuildDb")} checked={props.rebuildDb} onChange={props.onRebuildDbChange} />
          <SwitchLabel label={t("admin.misskey.generateCache")} checked={props.generateCache} onChange={props.onGenerateCacheChange} />
          <SwitchLabel label={t("admin.misskey.dryRun")} checked={dryRun} onChange={props.onDryRunChange} />
        </div>

        {!hasCredential && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <span>{t("admin.misskey.tokenMissing")}</span>
          </div>
        )}

        <Button
          disabled={busy === "misskey" || !target.trim() || !hasCredential}
          onClick={onSync}
          className="w-full"
        >
          <RefreshCw className="h-4 w-4" /> {dryRun ? t("admin.misskey.startDryRun") : t("admin.misskey.startSync")}
        </Button>

        <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.misskey.note")}</p>
      </section>

      <aside className="space-y-6">
        <section className="space-y-3 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <KeyRound className="h-4 w-4" /> {t("admin.misskey.tokensTitle")}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">{t("admin.misskey.tokensDescription")}</p>
          </div>

          <div className="space-y-1.5">
            <Label>{t("admin.misskey.useSavedToken")}</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
              value={savedTokenId ? String(savedTokenId) : ""}
              onChange={(event) => onSavedTokenIdChange(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">{t("admin.misskey.noSavedToken")}</option>
              {activeTokens.map((token) => (
                <option key={token.id} value={String(token.id)}>
                  {tokenTitle(token)}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label>{t("admin.misskey.newToken")}</Label>
            <Input
              type="password"
              value={props.tokenDraft}
              placeholder={config?.token_configured ? t("admin.misskey.tokenFromConfig") : ""}
              onChange={(event) => props.onTokenDraftChange(event.target.value)}
            />
            <Input
              value={props.tokenLabel}
              placeholder={t("admin.misskey.tokenLabel")}
              onChange={(event) => props.onTokenLabelChange(event.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={busy === "misskey-token-save" || !props.tokenDraft.trim()}
              onClick={props.onSaveToken}
              className="w-full"
            >
              <Save className="h-4 w-4" /> {t("admin.misskey.saveToken")}
            </Button>
          </div>

          <div className="space-y-2">
            {savedTokens.length === 0 && <EmptyLine text={t("admin.misskey.emptyTokens")} />}
            {savedTokens.map((token) => (
              <div
                key={token.id}
                className={cn(
                  "space-y-2 rounded-md border border-border p-3 text-xs",
                  !token.is_active && "opacity-60"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate font-medium" title={tokenTitle(token)}>
                    {tokenTitle(token)}
                  </span>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {token.is_active ? token.host : t("admin.misskey.revoked")}
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {token.last_used_at
                    ? t("admin.misskey.lastUsed", { at: formatDate(token.last_used_at) })
                    : t("admin.misskey.neverUsed")}
                </div>
                {token.is_active && (
                  <div className="flex gap-2">
                    <Input
                      value={props.tokenLabelDrafts[token.id] ?? token.label}
                      placeholder={t("admin.misskey.tokenLabel")}
                      onChange={(event) =>
                        props.onTokenLabelDraftsChange((current) => ({ ...current, [token.id]: event.target.value }))
                      }
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy === `misskey-token-label-${token.id}`}
                      onClick={() => props.onUpdateTokenLabel(token.id)}
                    >
                      <Save className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy === `misskey-token-revoke-${token.id}`}
                      onClick={() => props.onRevokeToken(token.id)}
                    >
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
                <ListChecks className="h-4 w-4" /> {t("admin.misskey.logsTitle")}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {pollingMode === "active" && t("admin.misskey.pollingActive")}
                {pollingMode === "idle" && t("admin.misskey.pollingIdle")}
                {pollingMode === "paused" && t("admin.misskey.pollingPaused")}
                {lastUpdatedAt && ` · ${formatDate(lastUpdatedAt)}`}
              </p>
            </div>
            <Button variant="outline" size="sm" disabled={busy === "misskey-log-refresh"} onClick={onRefreshLogs}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          <div className="max-h-[520px] space-y-2 overflow-auto">
            {logs.map((log) => <MisskeyLogRow key={log.id} log={log} />)}
            {logs.length === 0 && <EmptyLine text={t("admin.misskey.emptyLogs")} />}
          </div>
        </section>
      </aside>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  allowEmpty = false,
  hint,
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
          const bounded = Math.min(max ?? Number.MAX_SAFE_INTEGER, Math.max(min ?? 0, parsed));
          onChange(bounded);
        }}
      />
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function tokenTitle(token: MisskeyTokenSummary): string {
  const account = token.misskey_username ? `@${token.misskey_username}` : "";
  const masked = `${token.token_prefix}…${token.token_suffix}`;
  return [token.label, account, masked].filter(Boolean).join(" · ");
}
