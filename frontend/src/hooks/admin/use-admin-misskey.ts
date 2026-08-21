"use client";

import { useCallback, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { MisskeyConfigResponse, MisskeySyncOptions, MisskeyTokenSummary } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

type UseAdminMisskeyOptions = {
  run: AdminActionRunner;
  onError: (message: string) => void;
  username: string;
};

export function useAdminMisskey({ run, onError, username }: UseAdminMisskeyOptions) {
  const { t } = useI18n();
  const [config, setConfig] = useState<MisskeyConfigResponse | null>(null);
  const [target, setTarget] = useState("");
  const [host, setHost] = useState("");
  const [limit, setLimit] = useState<number | "">(100);
  const [pageSize, setPageSize] = useState(100);
  const [maxPages, setMaxPages] = useState<number | "">("");
  const [delay, setDelay] = useState(1);
  const [downloadConcurrency, setDownloadConcurrency] = useState(5);
  const [storageStrategy, setStorageStrategy] = useState("");
  const [includeReplies, setIncludeReplies] = useState(true);
  const [backfill, setBackfill] = useState(true);
  const [downloadMedia, setDownloadMedia] = useState(true);
  const [rebuildDb, setRebuildDb] = useState(true);
  const [generateCache, setGenerateCache] = useState(true);
  const [dryRun, setDryRun] = useState(false);

  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenLabel, setTokenLabel] = useState("");
  const [savedTokenId, setSavedTokenId] = useState<number | null>(null);
  const [savedTokens, setSavedTokens] = useState<MisskeyTokenSummary[]>([]);
  const [tokenLabelDrafts, setTokenLabelDrafts] = useState<Record<number, string>>({});

  const loadConfig = useCallback(async () => {
    try {
      const response = await NyaApi.misskeyConfig();
      setConfig(response);
      setHost((current) => current || response.host);
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

  const loadTokensFor = useCallback(
    async (owner: string, showError = true) => {
      if (!owner) return null;
      try {
        const response = await NyaApi.userMisskeyTokens(owner);
        setSavedTokens(response.items);
        return response.items;
      } catch (err) {
        if (showError) onError(err instanceof ApiError ? err.message : String(err));
        return null;
      }
    },
    [onError]
  );

  const saveCurrentToken = useCallback(async () => {
    const value = tokenDraft.trim();
    if (!value) {
      onError(t("admin.misskey.tokenMissing"));
      return;
    }
    const saved = await run(
      "misskey-token-save",
      () => NyaApi.saveMisskeyToken(username, {
        token: value,
        label: tokenLabel.trim(),
        host: (host || config?.host || "misskey.io").trim(),
      }),
      () => t("common.saved")
    );
    if (saved) {
      setTokenDraft("");
      setTokenLabel("");
      setSavedTokenId(saved.id);
      await loadTokensFor(username, false);
    }
  }, [config?.host, host, loadTokensFor, onError, run, t, tokenDraft, tokenLabel, username]);

  const updateTokenLabel = useCallback(
    async (tokenId: number) => {
      const label = tokenLabelDrafts[tokenId] ?? "";
      const updated = await run(
        `misskey-token-label-${tokenId}`,
        () => NyaApi.updateMisskeyToken(tokenId, label),
        () => t("common.saved")
      );
      if (updated) await loadTokensFor(username, false);
    },
    [loadTokensFor, run, t, tokenLabelDrafts, username]
  );

  const revokeToken = useCallback(
    async (tokenId: number) => {
      const revoked = await run(
        `misskey-token-revoke-${tokenId}`,
        () => NyaApi.revokeMisskeyToken(tokenId),
        () => t("admin.misskey.revoked")
      );
      if (revoked) {
        setSavedTokenId((current) => (current === tokenId ? null : current));
        await loadTokensFor(username, false);
      }
    },
    [loadTokensFor, run, t, username]
  );

  const buildOptions = useCallback((): MisskeySyncOptions => ({
    misskey_token_id: savedTokenId ?? undefined,
    token: savedTokenId ? undefined : tokenDraft.trim() || undefined,
    host: host.trim() || undefined,
    storage_strategy: storageStrategy || undefined,
    limit: limit === "" ? undefined : limit,
    page_size: pageSize,
    max_pages: maxPages === "" ? undefined : maxPages,
    include_replies: includeReplies,
    backfill,
    download_media: downloadMedia,
    download_concurrency: downloadConcurrency,
    request_delay_seconds: delay,
    rebuild_db: rebuildDb,
    generate_cache: generateCache,
    dry_run: dryRun,
  }), [
    backfill,
    delay,
    downloadConcurrency,
    downloadMedia,
    dryRun,
    generateCache,
    host,
    includeReplies,
    limit,
    maxPages,
    pageSize,
    rebuildDb,
    savedTokenId,
    storageStrategy,
    tokenDraft,
  ]);

  return {
    config,
    loadConfig,
    target,
    setTarget,
    host,
    setHost,
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
    includeReplies,
    setIncludeReplies,
    backfill,
    setBackfill,
    downloadMedia,
    setDownloadMedia,
    rebuildDb,
    setRebuildDb,
    generateCache,
    setGenerateCache,
    dryRun,
    setDryRun,
    tokenDraft,
    setTokenDraft,
    tokenLabel,
    setTokenLabel,
    savedTokenId,
    setSavedTokenId,
    savedTokens,
    tokenLabelDrafts,
    setTokenLabelDrafts,
    loadTokensFor,
    saveCurrentToken,
    updateTokenLabel,
    revokeToken,
    buildOptions,
  };
}
