"use client";

import type { Dispatch, SetStateAction } from "react";
import { Copy, ExternalLink, FolderInput, Globe2, KeyRound, ShieldAlert, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TextAreaField } from "@/components/admin/admin-fields";
import { PixivLogRow } from "@/components/admin/admin-operation-rows";
import { PixivCookieManager, PixivTokenManager } from "@/components/admin/pixiv-credential-managers";
import {
  SegmentedControl,
  StorageStrategySelect,
  SyncCard,
  SyncLogsSection,
  SyncNumberField,
  SyncPanelLayout,
  SyncSubmitButton,
  SyncSwitchGroup,
} from "@/components/admin/admin-sync-shared";
import { SwitchLabel } from "@/components/ui/switch-label";
import type { SyncBulkAction } from "@/components/admin/admin-sync-log-list";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
import { countPixivResults, type PixivTargetResult } from "@/lib/pixiv-targets";
import type { PixivAuthMode, PixivConfigResponse, PixivCookieSummary, PixivTokenSummary, UploadLogItem } from "@/lib/types";

type PixivMode = "pid" | "user";
type PixivSourceMode = "artist_works" | "bookmarks" | "following" | "search_tag" | "ranking";
import type { AdminPollingMode } from "@/hooks/admin/use-admin-operations";

type PixivVisibleSession = {
  id: string;
  status: string;
  message?: string | null;
  error?: string | null;
};

type AdminPixivPanelProps = {
  isAdmin: boolean;
  username?: string | null;
  busy: string | null;
  pixivConfig: PixivConfigResponse | null;
  pixivAuthMode: PixivAuthMode;
  onPixivAuthModeChange: (mode: PixivAuthMode) => void;
  pixivVisibleSession: PixivVisibleSession | null;
  pixivVisibleLoginDisabledReason: string;
  onStartVisiblePixivLogin: () => unknown;
  pixivRefreshToken: string;
  onPixivRefreshTokenChange: (value: string) => void;
  pixivSavedTokenId: number | null;
  onPixivSavedTokenIdChange: (value: number | null) => void;
  pixivTokenLabel: string;
  onPixivTokenLabelChange: (value: string) => void;
  pixivSavedTokens: PixivTokenSummary[];
  pixivTokenDrafts: Record<number, string>;
  onPixivTokenDraftsChange: Dispatch<SetStateAction<Record<number, string>>>;
  onSaveCurrentPixivToken: () => unknown;
  onUpdatePixivTokenLabel: (tokenId: number) => unknown;
  onRevokePixivSavedToken: (tokenId: number) => unknown;
  pixivOAuthCallback: string;
  onPixivOAuthCallbackChange: (value: string) => void;
  pixivOAuthVerifier: string;
  pixivOAuthUrl: string;
  pixivOAuthInputKind: string;
  pixivOAuthOpenInputUrl: string | null;
  pixivOAuthStartUrl: string | null;
  pixivOAuthHintText: string;
  onStartPixivOAuth: () => unknown;
  onExchangePixivOAuth: () => unknown;
  onCopyPixivStartUrl: (url: string) => unknown;
  pixivCookie: string;
  onPixivCookieChange: (value: string) => void;
  pixivSavedCookieId: number | null;
  onPixivSavedCookieIdChange: (value: number | null) => void;
  pixivCookieLabel: string;
  onPixivCookieLabelChange: (value: string) => void;
  pixivSavedCookies: PixivCookieSummary[];
  pixivCookieDrafts: Record<number, string>;
  onPixivCookieDraftsChange: Dispatch<SetStateAction<Record<number, string>>>;
  onSaveCurrentPixivCookie: () => unknown;
  onUpdatePixivCookieLabel: (cookieId: number) => unknown;
  onRevokePixivSavedCookie: (cookieId: number) => unknown;
  pixivMode: PixivMode;
  onPixivModeChange: (mode: PixivMode) => void;
  pid: string;
  onPidChange: (value: string) => void;
  pixivUid: string;
  onPixivUidChange: (value: string) => void;
  pixivLimit: number;
  onPixivLimitChange: (value: number) => void;
  pixivSourceMode: PixivSourceMode;
  onPixivSourceModeChange: (value: PixivSourceMode) => void;
  pixivRestrict: string;
  onPixivRestrictChange: (value: string) => void;
  pixivRebuildDb: boolean;
  onPixivRebuildDbChange: (value: boolean) => void;
  pixivGenerateCache: boolean;
  onPixivGenerateCacheChange: (value: boolean) => void;
  pixivDryRun: boolean;
  onPixivDryRunChange: (value: boolean) => void;
  pixivPublicFirst: boolean;
  onPixivPublicFirstChange: (value: boolean) => void;
  pixivMakePublic: boolean;
  onPixivMakePublicChange: (value: boolean) => void;
  pixivDelay: number;
  onPixivDelayChange: (value: number) => void;
  pixivConcurrency: number;
  onPixivConcurrencyChange: (value: number) => void;
  pixivStorageStrategy: string;
  onPixivStorageStrategyChange: (value: string) => void;
  pixivMaxRetries: number;
  onPixivMaxRetriesChange: (value: number) => void;
  pixivRetryBase: number;
  onPixivRetryBaseChange: (value: number) => void;
  pixivRetryMax: number;
  onPixivRetryMaxChange: (value: number) => void;
  onSyncPixiv: () => unknown;
  pixivTargetResults: PixivTargetResult[];
  pixivLogs: UploadLogItem[];
  pixivPollingMode: AdminPollingMode;
  pixivLastUpdatedAt: string | null;
  onRefreshPixivLogs: () => unknown;
  onSyncBulkAction: (action: SyncBulkAction, assetKeys: string[]) => unknown;
  onRetryPixiv: (target: string, kind: string) => unknown;
};

export function AdminPixivPanel({
  isAdmin,
  username,
  busy,
  pixivConfig,
  pixivAuthMode,
  onPixivAuthModeChange,
  pixivVisibleSession,
  pixivVisibleLoginDisabledReason,
  onStartVisiblePixivLogin,
  pixivRefreshToken,
  onPixivRefreshTokenChange,
  pixivSavedTokenId,
  onPixivSavedTokenIdChange,
  pixivTokenLabel,
  onPixivTokenLabelChange,
  pixivSavedTokens,
  pixivTokenDrafts,
  onPixivTokenDraftsChange,
  onSaveCurrentPixivToken,
  onUpdatePixivTokenLabel,
  onRevokePixivSavedToken,
  pixivOAuthCallback,
  onPixivOAuthCallbackChange,
  pixivOAuthVerifier,
  pixivOAuthUrl,
  pixivOAuthInputKind,
  pixivOAuthOpenInputUrl,
  pixivOAuthStartUrl,
  pixivOAuthHintText,
  onStartPixivOAuth,
  onExchangePixivOAuth,
  onCopyPixivStartUrl,
  pixivCookie,
  onPixivCookieChange,
  pixivSavedCookieId,
  onPixivSavedCookieIdChange,
  pixivCookieLabel,
  onPixivCookieLabelChange,
  pixivSavedCookies,
  pixivCookieDrafts,
  onPixivCookieDraftsChange,
  onSaveCurrentPixivCookie,
  onUpdatePixivCookieLabel,
  onRevokePixivSavedCookie,
  pixivMode,
  onPixivModeChange,
  pid,
  onPidChange,
  pixivUid,
  onPixivUidChange,
  pixivLimit,
  onPixivLimitChange,
  pixivSourceMode,
  onPixivSourceModeChange,
  pixivRestrict,
  onPixivRestrictChange,
  pixivRebuildDb,
  onPixivRebuildDbChange,
  pixivGenerateCache,
  onPixivGenerateCacheChange,
  pixivDryRun,
  onPixivDryRunChange,
  pixivPublicFirst,
  onPixivPublicFirstChange,
  pixivMakePublic,
  onPixivMakePublicChange,
  pixivDelay,
  onPixivDelayChange,
  pixivConcurrency,
  onPixivConcurrencyChange,
  pixivStorageStrategy,
  onPixivStorageStrategyChange,
  pixivMaxRetries,
  onPixivMaxRetriesChange,
  pixivRetryBase,
  onPixivRetryBaseChange,
  pixivRetryMax,
  onPixivRetryMaxChange,
  onSyncPixiv,
  pixivTargetResults,
  pixivLogs,
  pixivPollingMode,
  pixivLastUpdatedAt,
  onRefreshPixivLogs,
  onSyncBulkAction,
  onRetryPixiv,
}: AdminPixivPanelProps) {
  const { t } = useI18n();
  const canSaveToken = Boolean(pixivRefreshToken.trim() && username);
  const canSaveCookie = Boolean(pixivCookie.trim() && username);

  return (
    <SyncPanelLayout
      main={
        <SyncCard
          icon={Globe2}
          title={t("admin.pixiv.title")}
          description={pixivConfig?.has_env_refresh_token ? t("admin.pixiv.envTokenDetected") : t("admin.pixiv.publicHint")}
        >
          <SegmentedControl
            value={pixivMode}
            onChange={onPixivModeChange}
            options={[
              { value: "pid" as PixivMode, label: t("admin.pixiv.pidMode") },
              { value: "user" as PixivMode, label: t("admin.pixiv.uidMode") },
            ]}
          />

          {pixivMode === "pid" ? (
            <div className="space-y-1.5">
              <Label htmlFor="pid">{t("admin.pixiv.pidMode")}</Label>
              <textarea id="pid" value={pid} onChange={(e) => onPidChange(e.target.value)} placeholder={t("admin.pixiv.pidPlaceholder")} rows={3} className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-ring" />
              <p className="text-xs text-muted-foreground">{t("admin.pixiv.targetHint")}</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_uid">{t("admin.pixiv.uidMode")}</Label>
                <Input id="pixiv_uid" value={pixivUid} onChange={(e) => onPixivUidChange(e.target.value)} placeholder={t("admin.pixiv.uidPlaceholder")} />
              </div>
              <SyncNumberField label={t("admin.pixiv.limit")} value={pixivLimit} min={1} onChange={(value) => onPixivLimitChange(typeof value === "number" ? value : 1)} />
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>{t("admin.pixiv.sourceScope")}</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
              value={pixivSourceMode}
              onChange={(e) => onPixivSourceModeChange(e.target.value as PixivSourceMode)}
            >
              <option value="artist_works">{t("admin.pixiv.scopeArtistWorks")}</option>
              <option value="bookmarks">{t("admin.pixiv.scopeBookmarks")}</option>
              <option value="following" disabled>{t("admin.pixiv.scopeFollowing")}</option>
              <option value="search_tag" disabled>{t("admin.pixiv.scopeSearchTag")}</option>
              <option value="ranking" disabled>{t("admin.pixiv.scopeRanking")}</option>
            </select>
            {pixivSourceMode === "bookmarks" && (
              <div className="mt-2 flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">{t("admin.pixiv.restrictLabel")}</Label>
                <select
                  className="flex h-8 flex-1 rounded-md border border-input bg-transparent px-2 text-xs focus-ring"
                  value={pixivRestrict}
                  onChange={(e) => onPixivRestrictChange(e.target.value)}
                >
                  <option value="public">{t("admin.pixiv.restrictPublic")}</option>
                  <option value="private">{t("admin.pixiv.restrictPrivate")}</option>
                </select>
              </div>
            )}
          </div>

          <StorageStrategySelect
            label={t("pages.upload.storageStrategy")}
            value={pixivStorageStrategy}
            strategies={pixivConfig?.storage_strategies}
            onChange={onPixivStorageStrategyChange}
          />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <SyncNumberField label={t("admin.pixiv.requestDelay")} value={pixivDelay} min={0} step={0.5} suffix="s" onChange={(value) => onPixivDelayChange(typeof value === "number" ? value : 1)} />
            <SyncNumberField label={t("admin.security.concurrency")} value={pixivConcurrency} min={1} max={Math.max(1, pixivConfig?.max_concurrency ?? 1)} onChange={(value) => onPixivConcurrencyChange(typeof value === "number" ? value : 1)} />
            <SyncNumberField label={t("admin.pixiv.maxRetries")} value={pixivMaxRetries} min={0} onChange={(value) => onPixivMaxRetriesChange(typeof value === "number" ? value : 0)} />
            <SyncNumberField label={t("admin.pixiv.retryBase")} value={pixivRetryBase} min={0} suffix="s" onChange={(value) => onPixivRetryBaseChange(typeof value === "number" ? value : 0)} />
            <SyncNumberField label={t("admin.pixiv.retryMax")} value={pixivRetryMax} min={0} suffix="s" onChange={(value) => onPixivRetryMaxChange(typeof value === "number" ? value : 0)} />
          </div>

          <SyncSwitchGroup>
            <SwitchLabel label={t("admin.pixiv.rebuildAfterSync")} checked={pixivRebuildDb} onChange={onPixivRebuildDbChange} />
            <SwitchLabel label={t("admin.pixiv.queueTranscode")} checked={pixivGenerateCache} onChange={onPixivGenerateCacheChange} />
            <SwitchLabel label={t("admin.pixiv.publicFirst")} checked={pixivPublicFirst} onChange={onPixivPublicFirstChange} />
            <SwitchLabel label={t("admin.pixiv.makePublic")} checked={pixivMakePublic} onChange={onPixivMakePublicChange} />
            <SwitchLabel label={t("admin.pixiv.dryRun")} checked={pixivDryRun} onChange={onPixivDryRunChange} />
          </SyncSwitchGroup>

          <SyncSubmitButton
            busy={busy === "pixiv"}
            disabled={pixivAuthMode === "local_import" || (pixivMode === "pid" ? !pid.trim() : !pixivUid.trim())}
            dryRun={pixivDryRun}
            label={t("admin.pixiv.startSync")}
            dryRunLabel={t("admin.pixiv.startDryRun")}
            onClick={onSyncPixiv}
          />
        </SyncCard>
      }
      side={
        <SyncCard icon={KeyRound} title={t("admin.pixiv.authTitle")}>
          <div className="flex items-start gap-2 rounded-md border border-border bg-muted/35 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
            {pixivConfig?.secret_encryption_enabled ? (
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            )}
            <span>
              {pixivConfig?.secret_encryption_enabled
                ? t("admin.pixiv.encryptionEnabled")
                : t("admin.pixiv.encryptionDisabled")}
            </span>
          </div>

          <SegmentedControl
            value={pixivAuthMode}
            onChange={onPixivAuthModeChange}
            className="grid grid-cols-3"
            options={[
              { value: "public" as PixivAuthMode, label: t("admin.pixiv.auth.public") },
              ...(isAdmin ? [{ value: "oauth_local" as PixivAuthMode, label: "OAuth" }] : []),
              { value: "refresh_token" as PixivAuthMode, label: "Token" },
              { value: "cookie" as PixivAuthMode, label: "Cookie" },
              ...(isAdmin ? [{ value: "oauth_manual" as PixivAuthMode, label: t("admin.pixiv.auth.manual") }] : []),
              { value: "local_import" as PixivAuthMode, label: t("admin.pixiv.auth.local") },
            ]}
          />
          {pixivAuthMode === "public" ? (
            <div className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
              <div className="font-medium text-foreground">{t("admin.pixiv.publicModeTitle")}</div>
              <div className="mt-1">
                {t("admin.pixiv.publicModeDescription")}
              </div>
              <div className="mt-1">
                {t("admin.pixiv.publicModeRateHint")}
              </div>
            </div>
          ) : pixivAuthMode === "oauth_local" ? (
            <div className="space-y-3 rounded-md border border-border bg-muted/25 p-3">
              <div className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                <div className="font-medium text-foreground">{t("admin.pixiv.visibleOauthTitle")}</div>
                <div className="mt-1">
                  {t("admin.pixiv.visibleOauthRequirement")}
                </div>
                <div className="mt-1">
                  {t("admin.pixiv.visibleOauthPasswordHint")}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span>{t("admin.pixiv.localVisibleLoginHint")}</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-[10px]"
                    disabled={Boolean(pixivVisibleLoginDisabledReason)}
                    onClick={onStartVisiblePixivLogin}
                    title={pixivVisibleLoginDisabledReason || undefined}
                  >
                    <ExternalLink className="h-3 w-3" /> {t("admin.pixiv.startVisibleLogin")}
                  </Button>
                </div>
              </div>
              <Button
                type="button"
                className="w-full"
                variant={pixivOAuthStartUrl ? "outline" : "default"}
                disabled={busy === "pixiv-oauth-start"}
                onClick={() => pixivOAuthStartUrl ? onCopyPixivStartUrl(pixivOAuthStartUrl) : onStartPixivOAuth()}
              >
                {pixivOAuthStartUrl ? <Copy className="h-4 w-4" /> : <ExternalLink className="h-4 w-4" />}
                {pixivOAuthStartUrl ? t("admin.pixiv.copyLoginUrl") : t("admin.pixiv.createLoginUrl")}
              </Button>
              {pixivVisibleSession && (
                <div className="rounded-md border border-border/70 bg-background/50 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                  {t("admin.pixiv.sessionStatus")}<span className="font-mono text-foreground">{pixivVisibleSession.status}</span>
                  {pixivVisibleSession.message ? <span> · {pixivVisibleSession.message}</span> : null}
                  {pixivVisibleSession.error ? <div className="text-destructive">{pixivVisibleSession.error}</div> : null}
                </div>
              )}
              {pixivConfig?.supports_browser_oauth_login === false && (
                <div className="rounded-md border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                  {t("admin.pixiv.pixivLoginMissing")}
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_oauth_local_token">OAuth Refresh Token</Label>
                <Input
                  id="pixiv_oauth_local_token"
                  type="password"
                  value={pixivRefreshToken}
                  onChange={(e) => onPixivRefreshTokenChange(e.target.value)}
                  placeholder={pixivConfig?.has_env_refresh_token ? t("admin.pixiv.useEnvPlaceholder") : t("admin.pixiv.pasteBrowserTokenPlaceholder")}
                />
              </div>
              <PixivTokenControls
                busy={busy}
                canSave={canSaveToken}
                tokens={pixivSavedTokens}
                selectedTokenId={pixivSavedTokenId}
                label={pixivTokenLabel}
                drafts={pixivTokenDrafts}
                onSelect={onPixivSavedTokenIdChange}
                onLabelChange={onPixivTokenLabelChange}
                onSave={onSaveCurrentPixivToken}
                onDraftChange={(tokenId, label) => onPixivTokenDraftsChange((drafts) => ({ ...drafts, [tokenId]: label }))}
                onUpdateLabel={onUpdatePixivTokenLabel}
                onRevoke={onRevokePixivSavedToken}
              />
            </div>
          ) : pixivAuthMode === "oauth_manual" ? (
            <div className="space-y-3 rounded-md border border-border bg-muted/25 p-3">
              <div className="rounded-md border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                {t("admin.pixiv.manualOauthHint")}
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                <Button type="button" variant="outline" disabled={busy === "pixiv-oauth-start"} onClick={onStartPixivOAuth}>
                  <ExternalLink className="h-4 w-4" /> {t("admin.pixiv.openPixivLogin")}
                </Button>
                <Button
                  type="button"
                  disabled={
                    busy === "pixiv-oauth-exchange" ||
                    !pixivOAuthVerifier.trim() ||
                    !pixivOAuthCallback.trim() ||
                    pixivOAuthInputKind === "login" ||
                    pixivOAuthInputKind === "start" ||
                    pixivOAuthInputKind === "post_redirect" ||
                    pixivOAuthInputKind === "third_party"
                  }
                  onClick={onExchangePixivOAuth}
                >
                  <KeyRound className="h-4 w-4" /> {t("admin.pixiv.exchangeToken")}
                </Button>
              </div>
              <TextAreaField
                label={t("admin.pixiv.callbackLabel")}
                value={pixivOAuthCallback}
                rows={3}
                onChange={onPixivOAuthCallbackChange}
              />
              <div className="rounded-md border border-border/70 bg-background/50 px-3 py-2 text-[11px] text-muted-foreground">
                {pixivOAuthHintText}
              </div>
              {pixivOAuthOpenInputUrl && (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => window.open(pixivOAuthOpenInputUrl, "_blank", "noopener,noreferrer")}
                  >
                    <ExternalLink className="h-4 w-4" /> {t("admin.pixiv.continuePixivRedirect")}
                  </Button>
                  {pixivOAuthStartUrl && (
                    <Button type="button" variant="outline" onClick={() => onCopyPixivStartUrl(pixivOAuthStartUrl)}>
                      <Copy className="h-4 w-4" /> {t("admin.pixiv.copyStartUrl")}
                    </Button>
                  )}
                </div>
              )}
              {pixivOAuthUrl && (
                <div className="space-y-1 rounded-md border border-border/70 bg-background/50 p-2">
                  <div className="text-[11px] text-muted-foreground">{t("admin.pixiv.backupLoginHint")}</div>
                  <a
                    href={pixivOAuthUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-xs text-primary hover:underline"
                  >
                    {pixivOAuthUrl}
                  </a>
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_oauth_token">Refresh Token</Label>
                <Input
                  id="pixiv_oauth_token"
                  type="password"
                  value={pixivRefreshToken}
                  onChange={(e) => onPixivRefreshTokenChange(e.target.value)}
                  placeholder={pixivConfig?.has_env_refresh_token ? t("admin.pixiv.useEnvPlaceholder") : t("admin.pixiv.autoFillAfterLogin")}
                />
              </div>
              <PixivTokenControls
                busy={busy}
                canSave={canSaveToken}
                tokens={pixivSavedTokens}
                selectedTokenId={pixivSavedTokenId}
                label={pixivTokenLabel}
                drafts={pixivTokenDrafts}
                onSelect={onPixivSavedTokenIdChange}
                onLabelChange={onPixivTokenLabelChange}
                onSave={onSaveCurrentPixivToken}
                onDraftChange={(tokenId, label) => onPixivTokenDraftsChange((drafts) => ({ ...drafts, [tokenId]: label }))}
                onUpdateLabel={onUpdatePixivTokenLabel}
                onRevoke={onRevokePixivSavedToken}
              />
            </div>
          ) : pixivAuthMode === "cookie" ? (
            <div className="space-y-3 rounded-md border border-border bg-muted/25 p-3">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="pixiv_cookie">{t("admin.pixiv.browserCookie")}</Label>
                  <a
                    href="/api/sync/pixiv/extension/download"
                    download
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium shadow-sm hover:bg-muted"
                  >
                    <ExternalLink className="h-3.5 w-3.5" /> {t("admin.pixiv.downloadExtension")}
                  </a>
                </div>
                <textarea
                  id="pixiv_cookie"
                  className="min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-ring"
                  rows={4}
                  value={pixivCookie}
                  onChange={(event) => onPixivCookieChange(event.target.value)}
                  placeholder="PHPSESSID=...; device_token=..."
                />
              </div>
              <PixivCookieManager
                cookies={pixivSavedCookies}
                selectedCookieId={pixivSavedCookieId}
                label={pixivCookieLabel}
                drafts={pixivCookieDrafts}
                busy={busy}
                canSave={canSaveCookie}
                onSelect={onPixivSavedCookieIdChange}
                onLabelChange={onPixivCookieLabelChange}
                onSave={onSaveCurrentPixivCookie}
                onDraftChange={(cookieId, label) => onPixivCookieDraftsChange((drafts) => ({ ...drafts, [cookieId]: label }))}
                onUpdateLabel={onUpdatePixivCookieLabel}
                onRevoke={onRevokePixivSavedCookie}
              />
            </div>
          ) : pixivAuthMode === "local_import" ? (
            <div className="rounded-md border border-border bg-muted/35 p-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-2 font-medium text-foreground">
                <FolderInput className="h-4 w-4" /> {t("admin.pixiv.localImport")}
              </div>
              <p className="mt-1">
                {t("admin.pixiv.localImportHint")}
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="pixiv_token">Refresh Token / OAuth Token</Label>
              <Input
                id="pixiv_token"
                type="password"
                value={pixivRefreshToken}
                onChange={(e) => onPixivRefreshTokenChange(e.target.value)}
                placeholder={pixivConfig?.has_env_refresh_token ? t("admin.pixiv.useEnvPlaceholder") : t("admin.pixiv.tokenRequiredPlaceholder")}
              />
              <PixivTokenControls
                busy={busy}
                canSave={canSaveToken}
                tokens={pixivSavedTokens}
                selectedTokenId={pixivSavedTokenId}
                label={pixivTokenLabel}
                drafts={pixivTokenDrafts}
                onSelect={onPixivSavedTokenIdChange}
                onLabelChange={onPixivTokenLabelChange}
                onSave={onSaveCurrentPixivToken}
                onDraftChange={(tokenId, label) => onPixivTokenDraftsChange((drafts) => ({ ...drafts, [tokenId]: label }))}
                onUpdateLabel={onUpdatePixivTokenLabel}
                onRevoke={onRevokePixivSavedToken}
              />
            </div>
          )}
        </SyncCard>
      }
      logs={
        <SyncLogsSection
          ns="admin.pixiv"
          logs={pixivLogs}
          bulkBusy={busy === "sync-bulk"}
          onBulkAction={onSyncBulkAction}
          renderRow={(log) => <PixivLogRow log={log} onRetry={onRetryPixiv} />}
          pollingMode={pixivPollingMode}
          lastUpdatedAt={pixivLastUpdatedAt}
          refreshing={busy === "pixiv-log-refresh"}
          onRefresh={onRefreshPixivLogs}
          before={
            <>
              {pixivTargetResults.length > 0 && (
                <div className="space-y-2 rounded-md border border-border bg-muted/25 p-3" aria-live="polite">
                  <h3 className="text-sm font-medium">{t("admin.pixiv.batchResults")}</h3>
                  <p className="text-xs text-muted-foreground">{t("admin.pixiv.batchSummary", countPixivResults(pixivTargetResults))}</p>
                  <div className="grid max-h-80 gap-2 overflow-auto pr-1 md:grid-cols-2">
                    {pixivTargetResults.map((item) => (
                      <div key={item.pid ?? item.input} className={cn("space-y-1 rounded-md border border-border bg-background p-2 text-xs", item.status === "error" && "border-destructive/35")}>
                        <div className="break-all font-medium">{item.input}</div>
                        <p>{t(`admin.pixiv.targetStatus.${item.status}`)}</p>
                        <p className="break-words text-muted-foreground">
                          {item.error ? t(`admin.pixiv.targetError.${item.error}`) : item.message}
                        </p>
                        {item.status === "error" && item.pid && (
                          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy === "pixiv"} onClick={() => onRetryPixiv(item.pid!, "pid")}>
                            {t("admin.pixiv.retryTarget")}
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          }
        />
      }
    />
  );
}

type PixivTokenControlsProps = {
  tokens: PixivTokenSummary[];
  selectedTokenId: number | null;
  label: string;
  drafts: Record<number, string>;
  busy: string | null;
  canSave: boolean;
  onSelect: (value: number | null) => void;
  onLabelChange: (value: string) => void;
  onSave: () => unknown;
  onDraftChange: (tokenId: number, label: string) => void;
  onUpdateLabel: (tokenId: number) => unknown;
  onRevoke: (tokenId: number) => unknown;
};

function PixivTokenControls(props: PixivTokenControlsProps) {
  return <PixivTokenManager {...props} />;
}
