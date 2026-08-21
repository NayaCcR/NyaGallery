"use client";

import { useCallback, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { FanboxConfigResponse, FanboxSessionSummary, FanboxSyncOptions } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

export type FanboxSyncMode = "creator" | "posts";

type UseAdminFanboxOptions = {
  run: AdminActionRunner;
  onError: (message: string) => void;
  username: string;
};

export function useAdminFanbox({ run, onError, username }: UseAdminFanboxOptions) {
  const { t } = useI18n();
  const [config, setConfig] = useState<FanboxConfigResponse | null>(null);
  const [mode, setMode] = useState<FanboxSyncMode>("creator");
  const [target, setTarget] = useState("");
  const [targets, setTargets] = useState("");
  const [limit, setLimit] = useState<number | "">(100);
  const [pageSize, setPageSize] = useState(10);
  const [maxPages, setMaxPages] = useState<number | "">("");
  const [delay, setDelay] = useState(1);
  const [downloadConcurrency, setDownloadConcurrency] = useState(3);
  const [storageStrategy, setStorageStrategy] = useState("");
  const [backfill, setBackfill] = useState(true);
  const [downloadMedia, setDownloadMedia] = useState(true);
  const [downloadFiles, setDownloadFiles] = useState(true);
  const [rebuildDb, setRebuildDb] = useState(true);
  const [generateCache, setGenerateCache] = useState(true);
  const [dryRun, setDryRun] = useState(false);

  const [sessionDraft, setSessionDraft] = useState("");
  const [sessionLabel, setSessionLabel] = useState("");
  const [savedSessionId, setSavedSessionId] = useState<number | null>(null);
  const [savedSessions, setSavedSessions] = useState<FanboxSessionSummary[]>([]);
  const [sessionLabelDrafts, setSessionLabelDrafts] = useState<Record<number, string>>({});
  const [pixivCookieDraft, setPixivCookieDraft] = useState("");

  const loadConfig = useCallback(async () => {
    try {
      const response = await NyaApi.fanboxConfig();
      setConfig(response);
      setPageSize((current) => current || response.page_size);
      setDelay((current) => current || response.default_request_delay_seconds);
      setDownloadConcurrency((current) => current || response.download_concurrency);
      setStorageStrategy((current) => current || response.default_storage_strategy);
      return response;
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
      return null;
    }
  }, [onError]);

  const loadSessionsFor = useCallback(
    async (owner: string, showError = true) => {
      if (!owner) return null;
      try {
        const response = await NyaApi.userFanboxSessions(owner);
        setSavedSessions(response.items);
        return response.items;
      } catch (err) {
        if (showError) onError(err instanceof ApiError ? err.message : String(err));
        return null;
      }
    },
    [onError]
  );

  const saveCurrentSession = useCallback(async () => {
    const value = sessionDraft.trim();
    if (!value) {
      onError(t("admin.fanbox.sessionMissing"));
      return;
    }
    const saved = await run(
      "fanbox-session-save",
      () => NyaApi.saveFanboxSession(username, { session_id: value, label: sessionLabel.trim(), source: "manual" }),
      () => t("common.saved")
    );
    if (saved) {
      setSessionDraft("");
      setSessionLabel("");
      setSavedSessionId(saved.id);
      await loadSessionsFor(username, false);
    }
  }, [loadSessionsFor, onError, run, sessionDraft, sessionLabel, t, username]);

  /** Fanbox has no credential of its own to paste; this trades a Pixiv session for a FANBOXSESSID. */
  const loginWithPixivCookie = useCallback(async () => {
    const derived = await run(
      "fanbox-login",
      () => NyaApi.fanboxLogin({
        cookie: pixivCookieDraft.trim() || undefined,
        label: sessionLabel.trim(),
        save: true,
      }),
      () => t("admin.fanbox.loginDone")
    );
    if (derived) {
      setPixivCookieDraft("");
      setSessionLabel("");
      if (derived.saved) setSavedSessionId(derived.saved.id);
      await loadSessionsFor(username, false);
    }
  }, [loadSessionsFor, pixivCookieDraft, run, sessionLabel, t, username]);

  const updateSessionLabel = useCallback(
    async (sessionId: number) => {
      const label = sessionLabelDrafts[sessionId] ?? "";
      const updated = await run(
        `fanbox-session-label-${sessionId}`,
        () => NyaApi.updateFanboxSession(sessionId, label),
        () => t("common.saved")
      );
      if (updated) await loadSessionsFor(username, false);
    },
    [loadSessionsFor, run, sessionLabelDrafts, t, username]
  );

  const revokeSession = useCallback(
    async (sessionId: number) => {
      const revoked = await run(
        `fanbox-session-revoke-${sessionId}`,
        () => NyaApi.revokeFanboxSession(sessionId),
        () => t("admin.fanbox.revoked")
      );
      if (revoked) {
        setSavedSessionId((current) => (current === sessionId ? null : current));
        await loadSessionsFor(username, false);
      }
    },
    [loadSessionsFor, run, t, username]
  );

  const buildOptions = useCallback((): FanboxSyncOptions => ({
    fanbox_session_id: savedSessionId ?? undefined,
    session_id: savedSessionId ? undefined : sessionDraft.trim() || undefined,
    storage_strategy: storageStrategy || undefined,
    limit: limit === "" ? undefined : limit,
    page_size: pageSize,
    max_pages: maxPages === "" ? undefined : maxPages,
    backfill,
    download_media: downloadMedia,
    download_files: downloadFiles,
    download_concurrency: downloadConcurrency,
    request_delay_seconds: delay,
    rebuild_db: rebuildDb,
    generate_cache: generateCache,
    dry_run: dryRun,
  }), [
    backfill,
    delay,
    downloadConcurrency,
    downloadFiles,
    downloadMedia,
    dryRun,
    generateCache,
    limit,
    maxPages,
    pageSize,
    rebuildDb,
    savedSessionId,
    sessionDraft,
    storageStrategy,
  ]);

  return {
    config,
    loadConfig,
    mode,
    setMode,
    target,
    setTarget,
    targets,
    setTargets,
    limit,
    setLimit,
    pageSize,
    setPageSize,
    maxPages,
    setMaxPages,
    delay,
    setDelay,
    downloadConcurrency,
    setDownloadConcurrency,
    storageStrategy,
    setStorageStrategy,
    backfill,
    setBackfill,
    downloadMedia,
    setDownloadMedia,
    downloadFiles,
    setDownloadFiles,
    rebuildDb,
    setRebuildDb,
    generateCache,
    setGenerateCache,
    dryRun,
    setDryRun,
    sessionDraft,
    setSessionDraft,
    sessionLabel,
    setSessionLabel,
    savedSessionId,
    setSavedSessionId,
    savedSessions,
    sessionLabelDrafts,
    setSessionLabelDrafts,
    pixivCookieDraft,
    setPixivCookieDraft,
    loadSessionsFor,
    saveCurrentSession,
    loginWithPixivCookie,
    updateSessionLabel,
    revokeSession,
    buildOptions,
  };
}
