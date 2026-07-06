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
  const sectionLabel = activeSection ? t(`admin.sections.${activeSection}`) : t("nav.admin");
  const sectionDescription = activeSection ? t(`admin.sections.descriptions.${activeSection}`) : "";

  const [pid, setPid] = useState("");
  const [pixivUid, setPixivUid] = useState("");
  const [pixivMode, setPixivMode] = useState<PixivMode>("pid");
  const [pixivSourceMode, setPixivSourceMode] = useState<PixivSourceMode>("artist_works");
  const [pixivRestrict, setPixivRestrict] = useState<string>("public");
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
        <h1 className="mb-2 text-lg font-semibold">{t("admin.page.checkingAuth")}</h1>
        <p className="text-sm text-muted-foreground">{t("admin.page.checkingAuthDescription")}</p>
      </div>
    );
  }

  if (!token) {
    return (
      <div className="container max-w-md py-16 text-center">
        <h1 className="mb-2 text-lg font-semibold">{t("common.loginRequired")}</h1>
        <p className="text-sm text-muted-foreground">{t("admin.page.loginDescription")}</p>
        <Button className="mt-4" onClick={() => router.push("/login")}>
          {t("auth.goLogin")}
        </Button>
      </div>
    );
  }

  async function startTranscode(assetKey: string) {
    await run(
      `transcode-${assetKey}`,
      () => NyaApi.startTranscode(assetKey),
      (result) => (result.status === "already_running" ? t("admin.page.transcodeAlreadyRunning") : t("admin.page.transcodeQueued"))
    );
    await refreshOperations(false);
  }

  async function cancelAllTranscode() {
    if (!window.confirm(t("admin.page.cancelAllTranscodeConfirm"))) return;
    await run(
      "cancel-all-transcode",
      () => NyaApi.cancelAllTranscode(),
      (result) => t("admin.page.cancelAllTranscodeDone", { count: result.cancelled })
    );
    await refreshOperations(false);
  }

  async function syncPixiv() {
    const auth_mode = pixivAuthMode;
    if (auth_mode === "local_import") {
      toast.error(t("admin.page.localImportSoon"));
      return;
    }
    if (auth_mode === "cookie" && !pixivSavedCookieId && !pixivCookie.trim()) {
      toast.error(t("admin.page.cookieRequired"));
      return;
    }
    if (
      ["refresh_token", "oauth", "oauth_local", "oauth_manual"].includes(auth_mode) &&
      !pixivSavedTokenId &&
      !pixivRefreshToken.trim() &&
      !pixivConfig?.has_env_refresh_token
    ) {
      toast.error(t("admin.page.tokenRequired"));
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
      restrict: pixivSourceMode === "bookmarks" ? pixivRestrict : undefined,
    };
    const result = await run(
      "pixiv",
      () => {
        if (pixivMode === "pid") return NyaApi.syncPixivPid(pid.trim(), options);
        if (pixivSourceMode === "bookmarks") return NyaApi.syncPixivBookmarks(pixivUid.trim(), options);
        return NyaApi.syncPixivUser(pixivUid.trim(), options);
      },
      (response) => pixivDryRun
        ? t("admin.page.dryRunDone", { count: response.preview?.length ?? 0 })
        : response.status === "queued"
          ? t("admin.page.queued", { id: response.sync_job_id ?? "queued" })
        : t("admin.page.syncDone", { files: response.sync.length, jobs: response.jobs?.length ?? 0 })
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
          <h1 className="text-xl font-semibold">{t("admin.page.title", { section: sectionLabel })}</h1>
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
              toast.success(t("admin.page.copiedStartUrl"));
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
            pixivRestrict={pixivRestrict}
            onPixivRestrictChange={setPixivRestrict}
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
            onRefreshPixivLogs={() => run("pixiv-log-refresh", () => refreshPixivLogs(), () => t("admin.page.pixivLogsRefreshed"))}
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
            onRefresh={() => run("ops-refresh", () => refreshOperations(), () => t("admin.page.opsRefreshed"))}
            onStartTranscode={startTranscode}
            onCancelAllTranscode={cancelAllTranscode}
          />
        )}

      {activeSection === "dashboard" && !isAdmin && (
        <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          {t("admin.dashboard.hiddenForRole", { role: me?.role ?? "unknown" })}
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
            onRefreshSecurity={() => run("security-refresh", loadSecurity, () => t("admin.page.securityRefreshed"))}
            onSaveSecurity={saveSecurity}
            onRefreshAccessLogs={() => run("access-log-refresh", loadSecurity, () => t("admin.page.accessLogsRefreshed"))}
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
            onRefreshConfig={() => run("developer-config-refresh", loadDeveloperConfig, () => t("admin.page.cloudStorageRefreshed"))}
            onSaveConfig={saveDeveloperConfig}
            onRebuild={() =>
              run("rebuild", () => NyaApi.rebuild(false), (r) =>
                t("admin.page.rebuildDone", { assets: r.assets, tags: r.tags, duplicates: r.duplicates })
              ).then((r) => r && setRebuildResult(JSON.stringify(r, null, 2)))
            }
            onRebuildWithCache={() =>
              run("rebuild-cache", () => NyaApi.rebuild(true), (r) =>
                t("admin.page.rebuildCacheDone", { assets: r.assets })
              ).then((r) => r && setRebuildResult(JSON.stringify(r, null, 2)))
            }
            onGenerateMedia={() => run("media", () => NyaApi.generateMedia(), () => t("admin.page.mediaGenerated"))}
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
            onRefreshTags={() => run("tag-refresh", loadTags, () => t("admin.page.tagsRefreshed"))}
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
            onRefreshConfig={() => run("developer-config-refresh", loadDeveloperConfig, () => t("admin.page.configRefreshed"))}
            onSaveConfig={saveDeveloperConfig}
            consoleStatus={consoleStatus}
            onRefreshConsole={() => run("developer-console-refresh", loadDeveloperConsole, () => t("admin.page.consoleRefreshed"))}
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
  const { t } = useI18n();
  const entries = sections.filter((section) => section !== "dashboard");

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div>
        <h2 className="text-sm font-medium">{t("admin.dashboard.title")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("admin.dashboard.currentRole", { role })}
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
                <span className="block font-medium">{t(`admin.sections.${section}`)}</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                  {t(`admin.sections.descriptions.${section}`)}
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
