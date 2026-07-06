"use client";

import { useEffect, type Dispatch, type SetStateAction } from "react";
import { Copy, ExternalLink, FolderInput, Globe2, KeyRound, ListChecks, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyLine, NumberField, TextAreaField, ToggleField } from "@/components/admin/admin-fields";
import { PixivLogRow } from "@/components/admin/admin-operation-rows";
import { formatDate } from "@/components/admin/admin-format";
import { PixivCookieManager, PixivTokenManager } from "@/components/admin/pixiv-credential-managers";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
import type { PixivAuthMode, PixivConfigResponse, PixivCookieSummary, PixivTokenSummary, UploadLogItem } from "@/lib/types";

type PixivMode = "pid" | "user";
type PixivSourceMode = "artist_works" | "bookmarks" | "following" | "search_tag" | "ranking";
type AdminPollingMode = "active" | "idle" | "paused";

type PixivLoginDraft = {
  username: string;
  password: string;
};

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
  pixivLoginDraft: PixivLoginDraft;
  onPixivLoginDraftChange: Dispatch<SetStateAction<PixivLoginDraft>>;
  pixivVisibleSession: PixivVisibleSession | null;
  pixivVisibleLoginDisabledReason: string;
  pixivBrowserLoginDisabledReason: string;
  onStartVisiblePixivLogin: () => unknown;
  onLoginPixivInBrowser: () => unknown;
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
  pixivLogs: UploadLogItem[];
  pixivPollingMode: AdminPollingMode;
  pixivLastUpdatedAt: string | null;
  onRefreshPixivLogs: () => unknown;
};

export function AdminPixivPanel({
  isAdmin,
  username,
  busy,
  pixivConfig,
  pixivAuthMode,
  onPixivAuthModeChange,
  pixivLoginDraft,
  onPixivLoginDraftChange,
  pixivVisibleSession,
  pixivVisibleLoginDisabledReason,
  pixivBrowserLoginDisabledReason,
  onStartVisiblePixivLogin,
  onLoginPixivInBrowser,
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
  pixivLogs,
  pixivPollingMode,
  pixivLastUpdatedAt,
  onRefreshPixivLogs,
}: AdminPixivPanelProps) {
  const { t } = useI18n();
  const canSaveToken = Boolean(pixivRefreshToken.trim() && username);
  const canSaveCookie = Boolean(pixivCookie.trim() && username);

  return (
    <aside className="space-y-4">
      <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Globe2 className="h-4 w-4" /> {t("admin.pixiv.title")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {pixivConfig?.has_env_refresh_token ? t("admin.pixiv.envTokenDetected") : t("admin.pixiv.publicHint")}
          </p>
        </div>

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

        <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-muted/40 p-1">
          {[
            ["public", t("admin.pixiv.auth.public")],
            ...(isAdmin ? [["oauth_local", "OAuth"]] : []),
            ["refresh_token", "Token"],
            ["cookie", "Cookie"],
            ...(isAdmin ? [["oauth_manual", t("admin.pixiv.auth.manual")]] : []),
            ["local_import", t("admin.pixiv.auth.local")],
          ].map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => onPixivAuthModeChange(mode as PixivAuthMode)}
              className={cn("h-8 rounded-md text-xs font-medium", pixivAuthMode === mode ? "bg-background shadow-sm" : "text-muted-foreground")}
            >
              {label}
            </button>
          ))}
        </div>

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
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_login_username">{t("admin.pixiv.pixivId")}</Label>
                <Input
                  id="pixiv_login_username"
                  value={pixivLoginDraft.username}
                  onChange={(e) => onPixivLoginDraftChange((draft) => ({ ...draft, username: e.target.value }))}
                  placeholder={t("admin.pixiv.pixivIdPlaceholder")}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_login_password">{t("admin.pixiv.pixivPassword")}</Label>
                <Input
                  id="pixiv_login_password"
                  type="password"
                  value={pixivLoginDraft.password}
                  onChange={(e) => onPixivLoginDraftChange((draft) => ({ ...draft, password: e.target.value }))}
                  placeholder={t("admin.pixiv.pixivPasswordPlaceholder")}
                />
              </div>
            </div>
            <Button
              type="button"
              className="w-full"
              disabled={Boolean(pixivVisibleLoginDisabledReason)}
              onClick={onStartVisiblePixivLogin}
              title={pixivVisibleLoginDisabledReason || undefined}
            >
              <ExternalLink className="h-4 w-4" /> {t("admin.pixiv.startVisibleLogin")}
            </Button>
            {pixivVisibleSession && (
              <div className="rounded-md border border-border/70 bg-background/50 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                {t("admin.pixiv.sessionStatus")}<span className="font-mono text-foreground">{pixivVisibleSession.status}</span>
                {pixivVisibleSession.message ? <span> · {pixivVisibleSession.message}</span> : null}
                {pixivVisibleSession.error ? <div className="text-destructive">{pixivVisibleSession.error}</div> : null}
              </div>
            )}
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={Boolean(pixivBrowserLoginDisabledReason)}
              onClick={onLoginPixivInBrowser}
              title={pixivBrowserLoginDisabledReason || undefined}
            >
              <KeyRound className="h-4 w-4" /> {busy === "pixiv-oauth-browser-login" ? t("admin.pixiv.headlessTokenBusy") : t("admin.pixiv.headlessToken")}
            </Button>
            {pixivBrowserLoginDisabledReason && busy !== "pixiv-oauth-browser-login" && (
              <div className="text-[11px] text-muted-foreground">{pixivBrowserLoginDisabledReason}</div>
            )}
            {pixivConfig?.supports_browser_oauth_login === false && (
              <div className="rounded-md border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                {t("admin.pixiv.pixivLoginMissing")}
              </div>
            )}
            <div className="rounded-md border border-border/70 bg-background/50 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
              {t("admin.pixiv.cliLoginHint")}
              <div className="mt-1 font-mono text-[10px] text-foreground">nyagallery --storage storage pixiv-login-browser --plain</div>
              {t("admin.pixiv.cliTokenHint")}
            </div>
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
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
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
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
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

        <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-muted/40 p-1">
          <button
            type="button"
            onClick={() => onPixivModeChange("pid")}
            className={cn("h-8 rounded-md text-xs font-medium", pixivMode === "pid" ? "bg-background shadow-sm" : "text-muted-foreground")}
          >
            {t("admin.pixiv.pidMode")}
          </button>
          <button
            type="button"
            onClick={() => onPixivModeChange("user")}
            className={cn("h-8 rounded-md text-xs font-medium", pixivMode === "user" ? "bg-background shadow-sm" : "text-muted-foreground")}
          >
            {t("admin.pixiv.uidMode")}
          </button>
        </div>

        {pixivMode === "pid" ? (
          <div className="space-y-1.5">
            <Label htmlFor="pid">{t("admin.pixiv.pidMode")}</Label>
            <Input id="pid" value={pid} onChange={(e) => onPidChange(e.target.value)} placeholder={t("admin.pixiv.pidPlaceholder")} />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-[1fr_110px] xl:grid-cols-1">
            <div className="space-y-1.5">
              <Label htmlFor="pixiv_uid">{t("admin.pixiv.uidMode")}</Label>
              <Input id="pixiv_uid" value={pixivUid} onChange={(e) => onPixivUidChange(e.target.value)} placeholder={t("admin.pixiv.uidPlaceholder")} />
            </div>
            <NumberField label={t("admin.pixiv.limit")} value={pixivLimit} onChange={onPixivLimitChange} />
          </div>
        )}

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

        <div className="space-y-1.5">
          <Label>{t("pages.upload.storageStrategy")}</Label>
          <select
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
            value={pixivStorageStrategy}
            onChange={(e) => onPixivStorageStrategyChange(e.target.value)}
          >
            {(pixivConfig?.storage_strategies?.length ? pixivConfig.storage_strategies : [{ name: "local", type: "local", is_default: true, is_remote: false }]).map((strategy) => (
              <option key={strategy.name} value={strategy.name}>
                {strategy.name}{strategy.is_default ? ` (${t("common.defaultOption")})` : ""} · {strategy.type}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
          <ToggleField label={t("admin.pixiv.rebuildAfterSync")} checked={pixivRebuildDb} onChange={onPixivRebuildDbChange} />
          <ToggleField label={t("admin.pixiv.queueTranscode")} checked={pixivGenerateCache} onChange={onPixivGenerateCacheChange} />
          <ToggleField label={t("admin.pixiv.dryRun")} checked={pixivDryRun} onChange={onPixivDryRunChange} />
          <ToggleField label={t("admin.pixiv.publicFirst")} checked={pixivPublicFirst} onChange={onPixivPublicFirstChange} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <NumberField label={t("admin.pixiv.requestDelay")} value={pixivDelay} suffix="s" onChange={onPixivDelayChange} />
          <NumberField label={t("admin.security.concurrency")} value={pixivConcurrency} onChange={(value) => onPixivConcurrencyChange(Math.max(1, Math.min(value, pixivConfig?.max_concurrency ?? 1)))} />
          <NumberField label={t("admin.pixiv.maxRetries")} value={pixivMaxRetries} onChange={onPixivMaxRetriesChange} />
          <NumberField label={t("admin.pixiv.retryBase")} value={pixivRetryBase} suffix="s" onChange={onPixivRetryBaseChange} />
          <NumberField label={t("admin.pixiv.retryMax")} value={pixivRetryMax} suffix="s" onChange={onPixivRetryMaxChange} />
        </div>

        <Button
          disabled={busy === "pixiv" || pixivAuthMode === "local_import" || (pixivMode === "pid" ? !pid.trim() : !pixivUid.trim())}
          onClick={onSyncPixiv}
          className="w-full"
        >
          <RefreshCw className="h-4 w-4" /> {pixivDryRun ? t("admin.pixiv.startDryRun") : t("admin.pixiv.startSync")}
        </Button>
      </section>

      <section className="space-y-3 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <ListChecks className="h-4 w-4" /> {t("admin.pixiv.logsTitle")}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {pixivPollingMode === "active" && t("admin.pixiv.pollingActive")}
              {pixivPollingMode === "idle" && t("admin.pixiv.pollingIdle")}
              {pixivPollingMode === "paused" && t("admin.pixiv.pollingPaused")}
              {pixivLastUpdatedAt && ` · ${formatDate(pixivLastUpdatedAt)}`}
            </p>
          </div>
          <Button variant="outline" size="sm" disabled={busy === "pixiv-log-refresh"} onClick={onRefreshPixivLogs}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
        <div className="max-h-[520px] space-y-2 overflow-auto">
          {pixivLogs.map((log) => <PixivLogRow key={log.id} log={log} />)}
          {pixivLogs.length === 0 && <EmptyLine text={t("admin.pixiv.emptyLogs")} />}
        </div>
      </section>
    </aside>
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
