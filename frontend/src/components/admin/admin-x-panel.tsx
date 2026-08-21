"use client";

import type { Dispatch, SetStateAction } from "react";
import { Hash, KeyRound, ListChecks, RefreshCw, Save, ShieldAlert, Trash2 } from "lucide-react";
import { EmptyLine } from "@/components/admin/admin-fields";
import { formatDate } from "@/components/admin/admin-format";
import { XLogRow } from "@/components/admin/admin-operation-rows";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SwitchLabel } from "@/components/ui/switch-label";
import { cn } from "@/lib/utils";
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
  onRetryFailed?: (targets: string[]) => unknown;
};

export function AdminXPanel(props: AdminXPanelProps) {
  const { t } = useI18n();
  const {
    busy,
    config,
    mode,
    onModeChange,
    target,
    onTargetChange,
    targets,
    onTargetsChange,
    savedTokens,
    savedTokenId,
    onSavedTokenIdChange,
    logs,
    pollingMode,
    lastUpdatedAt,
    onRefreshLogs,
    onRetryFailed,
    onSync,
    dryRun,
  } = props;
  const activeTokens = savedTokens.filter((token) => token.is_active);
  const hasSession = Boolean(savedTokenId || (props.tokenDraft.trim() && props.ct0Draft.trim()) || config?.session_configured);
  const canSubmit = mode === "user" ? Boolean(target.trim()) && hasSession : Boolean(targets.trim());

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Hash className="h-4 w-4" /> {t("admin.x.syncTitle")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("admin.x.syncDescription")}</p>
        </div>

        <div className="flex gap-2">
          {(["posts", "user"] as XSyncMode[]).map((value) => (
            <Button
              key={value}
              variant={mode === value ? "default" : "outline"}
              size="sm"
              onClick={() => onModeChange(value)}
            >
              {t(`admin.x.mode.${value}`)}
            </Button>
          ))}
        </div>

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

        {mode === "user" && (
          <div className="grid gap-3 md:grid-cols-3">
            <NumberField
              label={t("admin.x.limit")}
              value={props.limit}
              min={1}
              allowEmpty
              onChange={props.onLimitChange}
              hint={t("admin.x.limitHint")}
            />
            <NumberField
              label={t("admin.x.pageSize")}
              value={props.pageSize}
              min={1}
              max={100}
              onChange={(value) => props.onPageSizeChange(typeof value === "number" ? value : 20)}
              hint={t("admin.x.pageSizeHint")}
            />
            <NumberField
              label={t("admin.x.maxPages")}
              value={props.maxPages}
              min={1}
              allowEmpty
              onChange={props.onMaxPagesChange}
              hint={t("admin.x.maxPagesHint")}
            />
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-3">
          <NumberField
            label={t("admin.x.delay")}
            value={props.delay}
            min={0}
            step={0.5}
            onChange={(value) => props.onDelayChange(typeof value === "number" ? value : 2)}
            hint={t("admin.x.delayHint")}
          />
          <NumberField
            label={t("admin.x.downloadConcurrency")}
            value={props.downloadConcurrency}
            min={1}
            max={16}
            onChange={(value) => props.onDownloadConcurrencyChange(typeof value === "number" ? value : 4)}
          />
          <div className="space-y-1.5">
            <Label>{t("admin.x.storageStrategy")}</Label>
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
          <SwitchLabel label={t("admin.x.dryRun")} checked={dryRun} onChange={props.onDryRunChange} />
        </div>

        {mode === "user" && !hasSession && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <span>{t("admin.x.sessionRequired")}</span>
          </div>
        )}

        <Button disabled={busy === "x" || !canSubmit} onClick={onSync} className="w-full">
          <RefreshCw className="h-4 w-4" /> {dryRun ? t("admin.x.startDryRun") : t("admin.x.startSync")}
        </Button>

        <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.x.note")}</p>
      </section>

      <aside className="space-y-6">
        <section className="space-y-3 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <KeyRound className="h-4 w-4" /> {t("admin.x.tokensTitle")}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">{t("admin.x.tokensDescription")}</p>
          </div>

          <div className="space-y-1.5">
            <Label>{t("admin.x.useSavedToken")}</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
              value={savedTokenId ? String(savedTokenId) : ""}
              onChange={(event) => onSavedTokenIdChange(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">{t("admin.x.noSavedToken")}</option>
              {activeTokens.map((token) => (
                <option key={token.id} value={String(token.id)}>
                  {tokenTitle(token)}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label>{t("admin.x.newToken")}</Label>
            <Input
              type="password"
              value={props.tokenDraft}
              placeholder={config?.session_configured ? t("admin.x.tokenFromConfig") : "auth_token"}
              onChange={(event) => props.onTokenDraftChange(event.target.value)}
            />
            <Input
              type="password"
              value={props.ct0Draft}
              placeholder="ct0"
              onChange={(event) => props.onCt0DraftChange(event.target.value)}
            />
            <Input
              value={props.tokenLabel}
              placeholder={t("admin.x.tokenLabel")}
              onChange={(event) => props.onTokenLabelChange(event.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={busy === "x-token-save" || !props.tokenDraft.trim()}
              onClick={props.onSaveToken}
              className="w-full"
            >
              <Save className="h-4 w-4" /> {t("admin.x.saveToken")}
            </Button>
            <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.x.tokenHelp")}</p>
          </div>

          <div className="space-y-2">
            {savedTokens.length === 0 && <EmptyLine text={t("admin.x.emptyTokens")} />}
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
                    {token.is_active ? (token.has_ct0 ? token.host : t("admin.x.missingCt0")) : t("admin.x.revoked")}
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {token.last_used_at
                    ? t("admin.x.lastUsed", { at: formatDate(token.last_used_at) })
                    : t("admin.x.neverUsed")}
                </div>
                {token.is_active && (
                  <div className="flex gap-2">
                    <Input
                      value={props.tokenLabelDrafts[token.id] ?? token.label}
                      placeholder={t("admin.x.tokenLabel")}
                      onChange={(event) =>
                        props.onTokenLabelDraftsChange((current) => ({ ...current, [token.id]: event.target.value }))
                      }
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy === `x-token-label-${token.id}`}
                      onClick={() => props.onUpdateTokenLabel(token.id)}
                    >
                      <Save className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy === `x-token-revoke-${token.id}`}
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
                <ListChecks className="h-4 w-4" /> {t("admin.x.logsTitle")}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {pollingMode === "active" && t("admin.x.pollingActive")}
                {pollingMode === "idle" && t("admin.x.pollingIdle")}
                {pollingMode === "paused" && t("admin.x.pollingPaused")}
                {lastUpdatedAt && ` · ${formatDate(lastUpdatedAt)}`}
              </p>
            </div>
            <Button variant="outline" size="sm" disabled={busy === "x-log-refresh"} onClick={onRefreshLogs}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          <div className="max-h-[520px] space-y-2 overflow-auto">
            {logs.map((log) => (
              <XLogRow
                key={log.id}
                log={log}
                onRetry={onRetryFailed ? (targets) => { onRetryFailed(targets); } : undefined}
              />
            ))}
            {logs.length === 0 && <EmptyLine text={t("admin.x.emptyLogs")} />}
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

function tokenTitle(token: XTokenSummary): string {
  const account = token.x_screen_name ? `@${token.x_screen_name}` : "";
  const masked = `${token.token_prefix}…${token.token_suffix}`;
  return [token.label, account, masked].filter(Boolean).join(" · ");
}
