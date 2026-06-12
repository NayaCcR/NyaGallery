"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ChevronRight,
  Database,
  Globe2,
  KeyRound,
  LayoutDashboard,
  Shield,
  Settings2,
  Tags,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AdminAccountsPanel } from "@/components/admin/admin-accounts-panel";
import { AdminDeveloperPanel } from "@/components/admin/admin-developer-panel";
import { AdminMaintenancePanel } from "@/components/admin/admin-maintenance-panel";
import { AdminOperationsPanel } from "@/components/admin/admin-operations-panel";
import { AdminPixivPanel } from "@/components/admin/admin-pixiv-panel";
import { AdminSecurityPanel } from "@/components/admin/admin-security-panel";
import { AdminTagsPanel } from "@/components/admin/admin-tags-panel";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import {
  canAccessAdminSection,
  getAdminSectionHref,
  getAdminSectionLabel,
  getAdminSectionsForRole,
  getVisibleAdminSection,
  normalizeAdminSection,
  type AdminSection,
} from "@/lib/admin-sections";
import { useAdminAccounts } from "@/hooks/admin/use-admin-accounts";
import { useAdminAction } from "@/hooks/admin/use-admin-action";
import { useAdminDeveloper } from "@/hooks/admin/use-admin-developer";
import { useAdminOperations } from "@/hooks/admin/use-admin-operations";
import { useAdminPixivCredentials } from "@/hooks/admin/use-admin-pixiv-credentials";
import { useAdminPixivLogs } from "@/hooks/admin/use-admin-pixiv-logs";
import { useAdminPixivOAuth } from "@/hooks/admin/use-admin-pixiv-oauth";
import { useAdminPixivSettings } from "@/hooks/admin/use-admin-pixiv-settings";
import { useAdminSecurity } from "@/hooks/admin/use-admin-security";
import { useAdminTags } from "@/hooks/admin/use-admin-tags";
import type { PixivAuthMode, Role } from "@/lib/types";

type PixivMode = "pid" | "user";
type PixivSourceMode = "artist_works" | "bookmarks" | "following" | "search_tag" | "ranking";

const ADMIN_SECTION_DESCRIPTIONS: Record<AdminSection, string> = {
  dashboard: "按角色汇总当前可用的管理入口。",
  pixiv: "Pixiv 同步、OAuth/Token/Cookie 凭据和抓取日志。",
  operations: "上传历史、转码队列和最近上传日志。",
  security: "安全开关、限流策略、访问日志与角色/用户额度。",
  tags: "标签别名、标签统计筛选与汇总导出。",
  maintenance: "数据库重建、媒体缓存生成和云储存配置。",
  accounts: "当前账号密码、API Token，以及管理员用户维护。",
  developer: "后端配置编辑、节点状态和开发者白名单维护动作。",
};

const ADMIN_SECTION_ICONS: Record<AdminSection, LucideIcon> = {
  dashboard: LayoutDashboard,
  pixiv: Globe2,
  operations: Activity,
  security: Shield,
  tags: Tags,
  maintenance: Database,
  accounts: KeyRound,
  developer: Settings2,
};

export default function AdminPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const { token, ready, me } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const isAdmin = Boolean(me?.permissions?.includes("admin"));
  const isDeveloper = Boolean(me?.permissions?.includes("developer"));
  const canPixivSync = canAccessAdminSection(me?.role, "pixiv");
  const rawSection = searchParams?.get("section");
  const requestedSection = normalizeAdminSection(rawSection);
  const activeSection = getVisibleAdminSection(me?.role, requestedSection);
  const allowedSections = getAdminSectionsForRole(me?.role);
  const sectionLabel = activeSection ? getAdminSectionLabel(activeSection) : t("nav.admin");
  const sectionDescription = activeSection ? ADMIN_SECTION_DESCRIPTIONS[activeSection] : "";

  const [pid, setPid] = useState("");
  const [pixivUid, setPixivUid] = useState("");
  const [pixivMode, setPixivMode] = useState<PixivMode>("pid");
  const [pixivSourceMode, setPixivSourceMode] = useState<PixivSourceMode>("artist_works");
  const [pixivAuthMode, setPixivAuthMode] = useState<PixivAuthMode>("public");
  const {
    logs: pixivLogs,
    pollingMode: pixivPollingMode,
    lastUpdatedAt: pixivLastUpdatedAt,
    refreshPixivLogs,
  } = useAdminPixivLogs({ enabled: !!token && canPixivSync && activeSection === "pixiv", onError: toast.error });
  const { busy, run } = useAdminAction({ onError: toast.error, onSuccess: toast.success });
  const [rebuildResult, setRebuildResult] = useState<string | null>(null);
  const {
    pixivConfig,
    pixivLimit,
    setPixivLimit,
    pixivRebuildDb,
    setPixivRebuildDb,
    pixivGenerateCache,
    setPixivGenerateCache,
    pixivDryRun,
    setPixivDryRun,
    pixivPublicFirst,
    setPixivPublicFirst,
    pixivDelay,
    setPixivDelay,
    pixivMaxRetries,
    setPixivMaxRetries,
    pixivRetryBase,
    setPixivRetryBase,
    pixivRetryMax,
    setPixivRetryMax,
    pixivConcurrency,
    setPixivConcurrency,
    pixivStorageStrategy,
    setPixivStorageStrategy,
    loadPixivConfig,
  } = useAdminPixivSettings({ onError: toast.error });
  const {
    setLastPixivUser,
    pixivRefreshToken,
    setPixivRefreshToken,
    pixivSavedTokenId,
    setPixivSavedTokenId,
    pixivTokenLabel,
    setPixivTokenLabel,
    pixivSavedTokens,
    pixivTokenDrafts,
    setPixivTokenDrafts,
    pixivSavedCookieId,
    setPixivSavedCookieId,
    pixivCookieLabel,
    setPixivCookieLabel,
    pixivSavedCookies,
    pixivCookieDrafts,
    setPixivCookieDrafts,
    pixivCookie,
    setPixivCookie,
    loadPixivTokensFor,
    loadPixivCookiesFor,
    saveCurrentPixivToken,
    saveCurrentPixivCookie,
    updatePixivTokenLabel,
    updatePixivCookieLabel,
    revokePixivSavedToken,
    revokePixivSavedCookie,
  } = useAdminPixivCredentials({
    run,
    onError: toast.error,
    username: me?.username ?? "",
  });
  const {
    pixivLoginDraft,
    setPixivLoginDraft,
    pixivVisibleSession,
    pixivOAuthCallback,
    setPixivOAuthCallback,
    pixivOAuthVerifier,
    pixivOAuthUrl,
    pixivOAuthInputKind,
    pixivOAuthOpenInputUrl,
    pixivOAuthStartUrl,
    pixivOAuthHintText,
    pixivBrowserLoginDisabledReason,
    pixivVisibleLoginDisabledReason,
    startPixivOAuth,
    exchangePixivOAuth,
    loginPixivInBrowser,
    startVisiblePixivLogin,
  } = useAdminPixivOAuth({
    busy,
    run,
    supportsBrowserOAuthLogin: pixivConfig?.supports_browser_oauth_login,
    setPixivRefreshToken,
    setLastPixivUser,
    onError: toast.error,
    onSuccess: toast.success,
  });
  const {
    newUser,
    setNewUser,
    passwordDraft,
    setPasswordDraft,
    userPasswordDrafts,
    setUserPasswordDrafts,
    users,
    replaceUsers,
    tokenTarget,
    setTokenTarget,
    tokenLabel,
    setTokenLabel,
    issuedToken,
    apiTokens,
    loadTokensFor,
    loadUserTokens,
    loadUsers,
    revokeUserToken,
    issueTokenForTarget,
    createUser,
    changePassword,
    resetUserPassword,
  } = useAdminAccounts({ run, onError: toast.error });
  const {
    filteredTags,
    tagFilter,
    setTagFilter,
    aliasDrafts,
    setAliasDrafts,
    summaryPath,
    loadTags,
    saveAliases,
    exportTagSummary,
  } = useAdminTags({ run });

  const {
    uploadHistory,
    uploadLogs,
    transcodeJobs,
    error: opsError,
    pollingMode: opsPollingMode,
    lastUpdatedAt: opsLastUpdatedAt,
    refreshOperations,
  } = useAdminOperations({
    enabled: !!token && canAccessAdminSection(me?.role, "operations") && activeSection === "operations",
    onError: toast.error,
  });
  const {
    securityDraft,
    accessLogs,
    accessLogFilter,
    setAccessLogFilter,
    roleLimitTarget,
    setRoleLimitTarget,
    userLimitTarget,
    setUserLimitTarget,
    loadSecurity,
    saveSecurity,
    patchSecurity,
    patchRoleLimit,
    patchUserLimit,
  } = useAdminSecurity({ run, onUsersLoaded: replaceUsers });
  const {
    configResponse,
    configDraft,
    setConfigDraft,
    loadDeveloperConfig,
    saveDeveloperConfig,
    consoleStatus,
    loadDeveloperConsole,
    consolePasswordDraft,
    setConsolePasswordDraft,
    resetConsolePassword,
  } = useAdminDeveloper({ run, onError: toast.error });

  useEffect(() => {
    if (!ready || !token || !activeSection) return;
    if (requestedSection !== activeSection || (rawSection && rawSection !== activeSection)) {
      router.replace(getAdminSectionHref(activeSection));
    }
  }, [activeSection, rawSection, ready, requestedSection, router, token]);

  useEffect(() => {
    if (!token || !isAdmin || activeSection !== "tags") return;
    void loadTags();
  }, [activeSection, isAdmin, loadTags, token]);

  useEffect(() => {
    if (!token || !isAdmin || activeSection !== "security") return;
    void loadSecurity();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection, isAdmin, token]);

  useEffect(() => {
    if (!token || !isAdmin || activeSection !== "accounts") return;
    void loadUsers();
  }, [activeSection, isAdmin, loadUsers, token]);

  useEffect(() => {
    if (!token || !isDeveloper || !activeSection) return;
    if (activeSection === "developer") {
      void loadDeveloperConfig();
      void loadDeveloperConsole();
      void loadUsers();
    }
    if (activeSection === "maintenance") {
      void loadDeveloperConfig();
    }
  }, [activeSection, isDeveloper, loadDeveloperConfig, loadDeveloperConsole, loadUsers, token]);

  useEffect(() => {
    if (!token || !canPixivSync || activeSection !== "pixiv") return;
    void loadPixivConfig();
  }, [activeSection, canPixivSync, loadPixivConfig, token]);

  useEffect(() => {
    if (!token || !me || me.role === "guest") return;
    setTokenTarget(me.username);
    void loadTokensFor(me.username, false);
    if (canPixivSync) {
      void loadPixivTokensFor(me.username, false);
      void loadPixivCookiesFor(me.username, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, me?.username, me?.role, canPixivSync]);

  useEffect(() => {
    if (!isAdmin && (pixivAuthMode === "oauth_local" || pixivAuthMode === "oauth_manual")) {
      setPixivAuthMode("public");
    }
  }, [isAdmin, pixivAuthMode]);

  if (!ready) {
    return (
      <div className="container max-w-md py-16 text-center">
        <h1 className="mb-2 text-lg font-semibold">正在验证权限</h1>
        <p className="text-sm text-muted-foreground">请稍候。</p>
      </div>
    );
  }

  if (!token) {
    return (
      <div className="container max-w-md py-16 text-center">
        <h1 className="mb-2 text-lg font-semibold">需要登录</h1>
        <p className="text-sm text-muted-foreground">上传历史和管理操作需要账号权限。</p>
        <Button className="mt-4" onClick={() => router.push("/login")}>
          去登录
        </Button>
      </div>
    );
  }

  async function startTranscode(assetKey: string) {
    await run(
      `transcode-${assetKey}`,
      () => NyaApi.startTranscode(assetKey),
      (result) => (result.status === "already_running" ? "已有转码任务在运行" : "已加入转码队列")
    );
    await refreshOperations(false);
  }

  async function syncPixiv() {
    const auth_mode = pixivAuthMode;
    if (auth_mode === "local_import") {
      toast.error("本地导入入口会在后续接入文件导入器；当前请使用上传页或 Token/Cookie 抓取。");
      return;
    }
    if (auth_mode === "cookie" && !pixivSavedCookieId && !pixivCookie.trim()) {
      toast.error("Cookie 抓取需要选择已保存 Cookie 或填入临时浏览器 Cookie。");
      return;
    }
    if (
      ["refresh_token", "oauth", "oauth_local", "oauth_manual"].includes(auth_mode) &&
      !pixivSavedTokenId &&
      !pixivRefreshToken.trim() &&
      !pixivConfig?.has_env_refresh_token
    ) {
      toast.error("未检测到 PIXIV_REFRESH_TOKEN，请填入 OAuth/Token，或切换 Cookie 临时抓取。");
      return;
    }
    const options = {
      auth_mode,
      refresh_token: pixivSavedTokenId ? undefined : pixivRefreshToken.trim() || undefined,
      pixiv_token_id: pixivSavedTokenId || undefined,
      cookie: auth_mode === "cookie" && !pixivSavedCookieId ? pixivCookie.trim() : undefined,
      pixiv_cookie_id: auth_mode === "cookie" ? pixivSavedCookieId || undefined : undefined,
      storage_strategy: pixivStorageStrategy,
      public_first: pixivPublicFirst,
      rebuild_db: pixivRebuildDb,
      generate_cache: pixivGenerateCache,
      limit: pixivMode === "user" ? pixivLimit : undefined,
      request_delay_seconds: pixivDelay,
      max_retries: pixivMaxRetries,
      retry_base_seconds: pixivRetryBase,
      retry_max_seconds: pixivRetryMax,
      concurrency: pixivConcurrency,
      dry_run: pixivDryRun,
    };
    const result = await run(
      "pixiv",
      () => pixivMode === "pid"
        ? NyaApi.syncPixivPid(pid.trim(), options)
        : NyaApi.syncPixivUser(pixivUid.trim(), options),
      (response) => pixivDryRun
        ? `预检完成 · ${response.preview?.length ?? 0} 个作品`
        : response.status === "queued"
          ? `已加入后台抓取 · ${response.sync_job_id ?? "queued"}`
        : `同步完成 · ${response.sync.length} 个文件 · 转码队列 ${response.jobs?.length ?? 0}`
    );
    if (result) {
      setRebuildResult(JSON.stringify(result, null, 2));
      qc.invalidateQueries({ queryKey: ["search"] });
      await refreshPixivLogs(false);
      await refreshOperations(false);
    }
  }

  return (
    <div className="container max-w-6xl space-y-6 py-10">
      <header className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary text-primary-foreground">
          <Database className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold">管理 / {sectionLabel}</h1>
          <p className="text-xs text-muted-foreground">
            {sectionDescription}
          </p>
        </div>
      </header>

      <div className="space-y-6">
        {activeSection === "dashboard" && (
          <AdminDashboard role={me?.role ?? "guest"} sections={allowedSections} />
        )}

        {activeSection === "pixiv" && canPixivSync && (
          <AdminPixivPanel
            isAdmin={isAdmin}
            username={me?.username}
            busy={busy}
            pixivConfig={pixivConfig}
            pixivAuthMode={pixivAuthMode}
            onPixivAuthModeChange={setPixivAuthMode}
            pixivLoginDraft={pixivLoginDraft}
            onPixivLoginDraftChange={setPixivLoginDraft}
            pixivVisibleSession={pixivVisibleSession}
            pixivVisibleLoginDisabledReason={pixivVisibleLoginDisabledReason}
            pixivBrowserLoginDisabledReason={pixivBrowserLoginDisabledReason}
            onStartVisiblePixivLogin={startVisiblePixivLogin}
            onLoginPixivInBrowser={loginPixivInBrowser}
            pixivRefreshToken={pixivRefreshToken}
            onPixivRefreshTokenChange={setPixivRefreshToken}
            pixivSavedTokenId={pixivSavedTokenId}
            onPixivSavedTokenIdChange={setPixivSavedTokenId}
            pixivTokenLabel={pixivTokenLabel}
            onPixivTokenLabelChange={setPixivTokenLabel}
            pixivSavedTokens={pixivSavedTokens}
            pixivTokenDrafts={pixivTokenDrafts}
            onPixivTokenDraftsChange={setPixivTokenDrafts}
            onSaveCurrentPixivToken={saveCurrentPixivToken}
            onUpdatePixivTokenLabel={updatePixivTokenLabel}
            onRevokePixivSavedToken={revokePixivSavedToken}
            pixivOAuthCallback={pixivOAuthCallback}
            onPixivOAuthCallbackChange={setPixivOAuthCallback}
            pixivOAuthVerifier={pixivOAuthVerifier}
            pixivOAuthUrl={pixivOAuthUrl}
            pixivOAuthInputKind={pixivOAuthInputKind}
            pixivOAuthOpenInputUrl={pixivOAuthOpenInputUrl}
            pixivOAuthStartUrl={pixivOAuthStartUrl}
            pixivOAuthHintText={pixivOAuthHintText}
            onStartPixivOAuth={startPixivOAuth}
            onExchangePixivOAuth={exchangePixivOAuth}
            onCopyPixivStartUrl={(url) => {
              void navigator.clipboard.writeText(url);
              toast.success("已复制 start URL");
            }}
            pixivCookie={pixivCookie}
            onPixivCookieChange={setPixivCookie}
            pixivSavedCookieId={pixivSavedCookieId}
            onPixivSavedCookieIdChange={setPixivSavedCookieId}
            pixivCookieLabel={pixivCookieLabel}
            onPixivCookieLabelChange={setPixivCookieLabel}
            pixivSavedCookies={pixivSavedCookies}
            pixivCookieDrafts={pixivCookieDrafts}
            onPixivCookieDraftsChange={setPixivCookieDrafts}
            onSaveCurrentPixivCookie={saveCurrentPixivCookie}
            onUpdatePixivCookieLabel={updatePixivCookieLabel}
            onRevokePixivSavedCookie={revokePixivSavedCookie}
            pixivMode={pixivMode}
            onPixivModeChange={setPixivMode}
            pid={pid}
            onPidChange={setPid}
            pixivUid={pixivUid}
            onPixivUidChange={setPixivUid}
            pixivLimit={pixivLimit}
            onPixivLimitChange={setPixivLimit}
            pixivSourceMode={pixivSourceMode}
            onPixivSourceModeChange={setPixivSourceMode}
            pixivRebuildDb={pixivRebuildDb}
            onPixivRebuildDbChange={setPixivRebuildDb}
            pixivGenerateCache={pixivGenerateCache}
            onPixivGenerateCacheChange={setPixivGenerateCache}
            pixivDryRun={pixivDryRun}
            onPixivDryRunChange={setPixivDryRun}
            pixivPublicFirst={pixivPublicFirst}
            onPixivPublicFirstChange={setPixivPublicFirst}
            pixivDelay={pixivDelay}
            onPixivDelayChange={setPixivDelay}
            pixivConcurrency={pixivConcurrency}
            onPixivConcurrencyChange={setPixivConcurrency}
            pixivStorageStrategy={pixivStorageStrategy}
            onPixivStorageStrategyChange={setPixivStorageStrategy}
            pixivMaxRetries={pixivMaxRetries}
            onPixivMaxRetriesChange={setPixivMaxRetries}
            pixivRetryBase={pixivRetryBase}
            onPixivRetryBaseChange={setPixivRetryBase}
            pixivRetryMax={pixivRetryMax}
            onPixivRetryMaxChange={setPixivRetryMax}
            onSyncPixiv={syncPixiv}
            pixivLogs={pixivLogs}
            pixivPollingMode={pixivPollingMode}
            pixivLastUpdatedAt={pixivLastUpdatedAt}
            onRefreshPixivLogs={() => run("pixiv-log-refresh", () => refreshPixivLogs(), () => "Pixiv 日志已刷新")}
          />
        )}

        <main className="space-y-6">
        {activeSection === "operations" && (
          <AdminOperationsPanel
            isAdmin={isAdmin}
            busy={busy}
            error={opsError}
            pollingMode={opsPollingMode}
            lastUpdatedAt={opsLastUpdatedAt}
            transcodeJobs={transcodeJobs}
            uploadHistory={uploadHistory}
            uploadLogs={uploadLogs}
            onRefresh={() => run("ops-refresh", () => refreshOperations(), () => "已刷新上传与转码")}
            onStartTranscode={startTranscode}
          />
        )}

      {activeSection === "dashboard" && !isAdmin && (
        <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          你的账号角色是 <span className="font-mono">{me?.role ?? "unknown"}</span>，管理操作已隐藏。
        </div>
      )}

      {isAdmin && (
        <>
          {activeSection === "security" && (
          <AdminSecurityPanel
            busy={busy}
            securityDraft={securityDraft}
            users={users}
            accessLogs={accessLogs}
            accessLogFilter={accessLogFilter}
            onAccessLogFilterChange={setAccessLogFilter}
            roleLimitTarget={roleLimitTarget}
            onRoleLimitTargetChange={setRoleLimitTarget}
            userLimitTarget={userLimitTarget}
            onUserLimitTargetChange={setUserLimitTarget}
            onRefreshSecurity={() => run("security-refresh", loadSecurity, () => "安全数据已刷新")}
            onSaveSecurity={saveSecurity}
            onRefreshAccessLogs={() => run("access-log-refresh", loadSecurity, () => "访问日志已刷新")}
            onPatchSecurity={patchSecurity}
            onPatchRoleLimit={patchRoleLimit}
            onPatchUserLimit={patchUserLimit}
          />
          )}

          {activeSection === "maintenance" && (
          <AdminMaintenancePanel
            busy={busy}
            rebuildResult={rebuildResult}
            isDeveloper={isDeveloper}
            configResponse={configResponse}
            configDraft={configDraft}
            onConfigDraftChange={setConfigDraft}
            onRefreshConfig={() => run("developer-config-refresh", loadDeveloperConfig, () => "云储存配置已刷新")}
            onSaveConfig={saveDeveloperConfig}
            onRebuild={() =>
              run("rebuild", () => NyaApi.rebuild(false), (r) =>
                `重建完成 · 资产 ${r.assets} · 标签 ${r.tags} · 重复 ${r.duplicates}`
              ).then((r) => r && setRebuildResult(JSON.stringify(r, null, 2)))
            }
            onRebuildWithCache={() =>
              run("rebuild-cache", () => NyaApi.rebuild(true), (r) =>
                `重建并刷新缓存完成 · 资产 ${r.assets}`
              ).then((r) => r && setRebuildResult(JSON.stringify(r, null, 2)))
            }
            onGenerateMedia={() => run("media", () => NyaApi.generateMedia(), () => "媒体缓存已生成")}
          />
          )}

          {activeSection === "tags" && (
          <AdminTagsPanel
            busy={busy}
            filteredTags={filteredTags}
            tagFilter={tagFilter}
            onTagFilterChange={setTagFilter}
            aliasDrafts={aliasDrafts}
            onAliasDraftsChange={setAliasDrafts}
            summaryPath={summaryPath}
            onRefreshTags={() => run("tag-refresh", loadTags, () => "标签已刷新")}
            onExportTagSummary={exportTagSummary}
            onSaveAliases={saveAliases}
          />
          )}

          {activeSection === "developer" && isDeveloper && (
          <AdminDeveloperPanel
            busy={busy}
            configResponse={configResponse}
            configDraft={configDraft}
            onConfigDraftChange={setConfigDraft}
            onRefreshConfig={() => run("developer-config-refresh", loadDeveloperConfig, () => "配置已刷新")}
            onSaveConfig={saveDeveloperConfig}
            consoleStatus={consoleStatus}
            onRefreshConsole={() => run("developer-console-refresh", loadDeveloperConsole, () => "操作台状态已刷新")}
            users={users}
            passwordDraft={consolePasswordDraft}
            onPasswordDraftChange={setConsolePasswordDraft}
            onResetPassword={resetConsolePassword}
          />
          )}

        </>
      )}

      {activeSection === "accounts" && (
        <AdminAccountsPanel
          isAdmin={isAdmin}
          isDeveloper={isDeveloper}
          currentUsername={me?.username ?? ""}
          busy={busy}
          newUser={newUser}
          onNewUserChange={setNewUser}
          onCreateUser={createUser}
          tokenTarget={tokenTarget}
          onTokenTargetChange={setTokenTarget}
          tokenLabel={tokenLabel}
          onTokenLabelChange={setTokenLabel}
          issuedToken={issuedToken}
          apiTokens={apiTokens}
          onLoadTokens={loadUserTokens}
          onIssueToken={issueTokenForTarget}
          onRevokeToken={revokeUserToken}
          passwordDraft={passwordDraft}
          onPasswordDraftChange={setPasswordDraft}
          users={users}
          userPasswordDrafts={userPasswordDrafts}
          onUserPasswordDraftsChange={setUserPasswordDrafts}
          onChangePassword={changePassword}
          onResetUserPassword={resetUserPassword}
        />
      )}
        </main>
      </div>
    </div>
  );
}

function AdminDashboard({ role, sections }: { role: Role; sections: AdminSection[] }) {
  const entries = sections.filter((section) => section !== "dashboard");

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div>
        <h2 className="text-sm font-medium">管理概览</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          当前角色为 <span className="font-mono">{role}</span>，侧边栏和本页入口只显示该角色可访问的模块。
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {entries.map((section) => {
          const Icon = ADMIN_SECTION_ICONS[section];
          return (
            <Link
              key={section}
              href={getAdminSectionHref(section)}
              className="group flex min-h-24 items-start gap-3 rounded-md border border-border bg-background p-4 text-sm transition-colors hover:border-primary/40 hover:bg-muted/40"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{getAdminSectionLabel(section)}</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                  {ADMIN_SECTION_DESCRIPTIONS[section]}
                </span>
              </span>
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
