"use client";

import type { Dispatch, SetStateAction } from "react";
import { Copy, ExternalLink, FolderInput, Globe2, KeyRound, ListChecks, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyLine, NumberField, TextAreaField, ToggleField } from "@/components/admin/admin-fields";
import { PixivLogRow } from "@/components/admin/admin-operation-rows";
import { formatDate } from "@/components/admin/admin-format";
import { PixivCookieManager, PixivTokenManager } from "@/components/admin/pixiv-credential-managers";
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
  const canSaveToken = Boolean(pixivRefreshToken.trim() && username);
  const canSaveCookie = Boolean(pixivCookie.trim() && username);

  return (
    <aside className="space-y-4">
      <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Globe2 className="h-4 w-4" /> Pixiv 配置
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {pixivConfig?.has_env_refresh_token ? "已检测到环境变量 PIXIV_REFRESH_TOKEN；公开作品仍建议免登录抓取。" : "公开作品可免登录抓取；Token/Cookie 仅用于账号相关来源。"}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-muted/40 p-1">
          {[
            ["public", "公开"],
            ...(isAdmin ? [["oauth_local", "OAuth"]] : []),
            ["refresh_token", "Token"],
            ["cookie", "Cookie"],
            ...(isAdmin ? [["oauth_manual", "手动"]] : []),
            ["local_import", "本地"],
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
            <div className="font-medium text-foreground">公开抓取：不使用 Pixiv 登录态。</div>
            <div className="mt-1">
              适合单作品和公开用户作品，包含公开可访问的 R-18/R-18G 信息。收藏夹、关注、私有上下文仍需要 OAuth 或 Cookie。
            </div>
            <div className="mt-1">
              公开模式通常比登录态更不容易触发 429；仍建议保留适度请求间隔，避免压 Pixiv。
            </div>
          </div>
        ) : pixivAuthMode === "oauth_local" ? (
          <div className="space-y-3 rounded-md border border-border bg-muted/25 p-3">
            <div className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
              <div className="font-medium text-foreground">主 OAuth 流程：启动可见 Pixiv 登录浏览器。</div>
              <div className="mt-1">
                需要服务器安装 <span className="font-mono">pixiv-login</span> 依赖。浏览器窗口会出现在运行后端的机器上；本地自部署可以直接完成验证码、Passkey 或 2FA。
              </div>
              <div className="mt-1">
                Pixiv ID/密码可留空，直接在弹出的 Pixiv 页面登录。公共服务器没有桌面环境时，请用可见浏览器命令或手动粘贴 Token。
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_login_username">Pixiv ID / 邮箱</Label>
                <Input
                  id="pixiv_login_username"
                  value={pixivLoginDraft.username}
                  onChange={(e) => onPixivLoginDraftChange((draft) => ({ ...draft, username: e.target.value }))}
                  placeholder="Pixiv ID 或邮箱"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pixiv_login_password">Pixiv 密码</Label>
                <Input
                  id="pixiv_login_password"
                  type="password"
                  value={pixivLoginDraft.password}
                  onChange={(e) => onPixivLoginDraftChange((draft) => ({ ...draft, password: e.target.value }))}
                  placeholder="仅用于本次 OAuth 登录"
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
              <ExternalLink className="h-4 w-4" /> 启动可见 Pixiv 登录
            </Button>
            {pixivVisibleSession && (
              <div className="rounded-md border border-border/70 bg-background/50 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                会话状态：<span className="font-mono text-foreground">{pixivVisibleSession.status}</span>
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
              <KeyRound className="h-4 w-4" /> {busy === "pixiv-oauth-browser-login" ? "正在无头获取 Token" : "无头快速获取 Token"}
            </Button>
            {pixivBrowserLoginDisabledReason && busy !== "pixiv-oauth-browser-login" && (
              <div className="text-[11px] text-muted-foreground">{pixivBrowserLoginDisabledReason}</div>
            )}
            {pixivConfig?.supports_browser_oauth_login === false && (
              <div className="rounded-md border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                当前后端未安装 pixiv-login。请在后端环境运行 <span className="font-mono">python -m pip install -e &quot;.[pixiv-login]&quot;</span> 后重启。
              </div>
            )}
            <div className="rounded-md border border-border/70 bg-background/50 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
              不想在网页输入 Pixiv 密码时，也可以在服务器或本机运行：
              <div className="mt-1 font-mono text-[10px] text-foreground">nyagallery --storage storage pixiv-login-browser --plain</div>
              Token 以短横线开头也可以直接粘贴；命令行同步参数请用 <span className="font-mono">--refresh-token=...</span> 或环境变量。
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pixiv_oauth_local_token">OAuth Refresh Token</Label>
              <Input
                id="pixiv_oauth_local_token"
                type="password"
                value={pixivRefreshToken}
                onChange={(e) => onPixivRefreshTokenChange(e.target.value)}
                placeholder={pixivConfig?.has_env_refresh_token ? "留空使用后端环境变量" : "粘贴 pixiv-login-browser 输出的 refresh token"}
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
              手动 callback/code 换 token 仅作为备用方案。Pixiv 网页跳转可能卡在 post-redirect 或跳到第三方 callback；稳定使用请回到 OAuth 标签运行本地浏览器登录助手。
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <Button type="button" variant="outline" disabled={busy === "pixiv-oauth-start"} onClick={onStartPixivOAuth}>
                <ExternalLink className="h-4 w-4" /> 打开 Pixiv 登录
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
                <KeyRound className="h-4 w-4" /> 换取 Token
              </Button>
            </div>
            <TextAreaField
              label="回调 URL / code / post-redirect"
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
                  <ExternalLink className="h-4 w-4" /> 继续 Pixiv 跳转
                </Button>
                {pixivOAuthStartUrl && (
                  <Button type="button" variant="outline" onClick={() => onCopyPixivStartUrl(pixivOAuthStartUrl)}>
                    <Copy className="h-4 w-4" /> 复制 start URL
                  </Button>
                )}
              </div>
            )}
            {pixivOAuthUrl && (
              <div className="space-y-1 rounded-md border border-border/70 bg-background/50 p-2">
                <div className="text-[11px] text-muted-foreground">备用登录入口，不是 callback。</div>
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
                placeholder={pixivConfig?.has_env_refresh_token ? "留空使用后端环境变量" : "登录换取后自动填入"}
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
                <Label htmlFor="pixiv_cookie">浏览器 Cookie</Label>
                <a
                  href="/api/sync/pixiv/extension/download"
                  download
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium shadow-sm hover:bg-muted"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> 下载插件
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
              <FolderInput className="h-4 w-4" /> 本地导入
            </div>
            <p className="mt-1">
              可先使用上传页导入 PixivBatchDownloader 命名文件；后续会接入 metadata manifest 导入。
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
              placeholder={pixivConfig?.has_env_refresh_token ? "留空使用后端环境变量" : "未配置环境变量时必填"}
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
            作品 PID
          </button>
          <button
            type="button"
            onClick={() => onPixivModeChange("user")}
            className={cn("h-8 rounded-md text-xs font-medium", pixivMode === "user" ? "bg-background shadow-sm" : "text-muted-foreground")}
          >
            用户 UID
          </button>
        </div>

        {pixivMode === "pid" ? (
          <div className="space-y-1.5">
            <Label htmlFor="pid">作品 PID</Label>
            <Input id="pid" value={pid} onChange={(e) => onPidChange(e.target.value)} placeholder="例如 123456" />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-[1fr_110px] xl:grid-cols-1">
            <div className="space-y-1.5">
              <Label htmlFor="pixiv_uid">用户 UID</Label>
              <Input id="pixiv_uid" value={pixivUid} onChange={(e) => onPixivUidChange(e.target.value)} placeholder="例如 1234567" />
            </div>
            <NumberField label="抓取上限" value={pixivLimit} onChange={onPixivLimitChange} />
          </div>
        )}

        <div className="space-y-1.5">
          <Label>来源范围</Label>
          <select
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
            value={pixivSourceMode}
            onChange={(e) => onPixivSourceModeChange(e.target.value as PixivSourceMode)}
          >
            <option value="artist_works">用户作品 / 单作品</option>
            <option value="bookmarks" disabled>收藏夹（预留）</option>
            <option value="following" disabled>关注新作（预留）</option>
            <option value="search_tag" disabled>标签搜索（预留）</option>
            <option value="ranking" disabled>排行榜（预留）</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <Label>Storage strategy</Label>
          <select
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
            value={pixivStorageStrategy}
            onChange={(e) => onPixivStorageStrategyChange(e.target.value)}
          >
            {(pixivConfig?.storage_strategies?.length ? pixivConfig.storage_strategies : [{ name: "local", type: "local", is_default: true, is_remote: false }]).map((strategy) => (
              <option key={strategy.name} value={strategy.name}>
                {strategy.name}{strategy.is_default ? " (default)" : ""} · {strategy.type}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
          <ToggleField label="同步后重建索引" checked={pixivRebuildDb} onChange={onPixivRebuildDbChange} />
          <ToggleField label="抓取后加入转码队列" checked={pixivGenerateCache} onChange={onPixivGenerateCacheChange} />
          <ToggleField label="仅预检作品信息" checked={pixivDryRun} onChange={onPixivDryRunChange} />
          <ToggleField label="优先公开抓取" checked={pixivPublicFirst} onChange={onPixivPublicFirstChange} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <NumberField label="请求间隔" value={pixivDelay} suffix="s" onChange={onPixivDelayChange} />
          <NumberField label="并发" value={pixivConcurrency} onChange={(value) => onPixivConcurrencyChange(Math.max(1, Math.min(value, pixivConfig?.max_concurrency ?? 1)))} />
          <NumberField label="重试次数" value={pixivMaxRetries} onChange={onPixivMaxRetriesChange} />
          <NumberField label="429 初始等待" value={pixivRetryBase} suffix="s" onChange={onPixivRetryBaseChange} />
          <NumberField label="429 最大等待" value={pixivRetryMax} suffix="s" onChange={onPixivRetryMaxChange} />
        </div>

        <Button
          disabled={busy === "pixiv" || pixivAuthMode === "local_import" || (pixivMode === "pid" ? !pid.trim() : !pixivUid.trim())}
          onClick={onSyncPixiv}
          className="w-full"
        >
          <RefreshCw className="h-4 w-4" /> {pixivDryRun ? "开始预检" : "开始抓取"}
        </Button>
      </section>

      <section className="space-y-3 rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <ListChecks className="h-4 w-4" /> 抓取日志
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {pixivPollingMode === "active" && "自动刷新：抓取中，5 秒"}
              {pixivPollingMode === "idle" && "自动刷新：空闲，20 秒"}
              {pixivPollingMode === "paused" && "自动刷新：页面隐藏时暂停"}
              {pixivLastUpdatedAt && ` · ${formatDate(pixivLastUpdatedAt)}`}
            </p>
          </div>
          <Button variant="outline" size="sm" disabled={busy === "pixiv-log-refresh"} onClick={onRefreshPixivLogs}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
        <div className="max-h-[520px] space-y-2 overflow-auto">
          {pixivLogs.map((log) => <PixivLogRow key={log.id} log={log} />)}
          {pixivLogs.length === 0 && <EmptyLine text="暂无 Pixiv 抓取日志" />}
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
