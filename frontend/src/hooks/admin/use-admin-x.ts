"use client";

import { useCallback, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { XConfigResponse, XSyncOptions, XTokenSummary } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

export type XSyncMode = "posts" | "user";

type UseAdminXOptions = {
  run: AdminActionRunner;
  onError: (message: string) => void;
  username: string;
};

export function useAdminX({ run, onError, username }: UseAdminXOptions) {
  const { t } = useI18n();
  const [config, setConfig] = useState<XConfigResponse | null>(null);
  const [mode, setMode] = useState<XSyncMode>("posts");
  const [target, setTarget] = useState("");
  const [targets, setTargets] = useState("");
  const [limit, setLimit] = useState<number | "">(100);
  const [pageSize, setPageSize] = useState(20);
  const [maxPages, setMaxPages] = useState<number | "">("");
  const [delay, setDelay] = useState(2);
  const [downloadConcurrency, setDownloadConcurrency] = useState(4);
  const [storageStrategy, setStorageStrategy] = useState("");
  const [includeReplies, setIncludeReplies] = useState(true);
  const [mediaOnly, setMediaOnly] = useState(false);
  const [backfill, setBackfill] = useState(true);
  const [downloadMedia, setDownloadMedia] = useState(true);
  const [rebuildDb, setRebuildDb] = useState(true);
  const [generateCache, setGenerateCache] = useState(true);
  const [dryRun, setDryRun] = useState(false);

  const [tokenDraft, setTokenDraft] = useState("");
  const [ct0Draft, setCt0Draft] = useState("");
  const [tokenLabel, setTokenLabel] = useState("");
  const [savedTokenId, setSavedTokenId] = useState<number | null>(null);
  const [savedTokens, setSavedTokens] = useState<XTokenSummary[]>([]);
  const [tokenLabelDrafts, setTokenLabelDrafts] = useState<Record<number, string>>({});

  const loadConfig = useCallback(async () => {
    try {
      const response = await NyaApi.xConfig();
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

  const loadTokensFor = useCallback(
    async (owner: string, showError = true) => {
      if (!owner) return null;
      try {
        const response = await NyaApi.userXTokens(owner);
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
      onError(t("admin.x.tokenMissing"));
      return;
    }
    const saved = await run(
      "x-token-save",
      () => NyaApi.saveXToken(username, {
        token: value,
        ct0: ct0Draft.trim(),
        label: tokenLabel.trim(),
        host: config?.host || "x.com",
      }),
      () => t("common.saved")
    );
    if (saved) {
      setTokenDraft("");
      setCt0Draft("");
      setTokenLabel("");
      setSavedTokenId(saved.id);
      await loadTokensFor(username, false);
    }
  }, [config?.host, ct0Draft, loadTokensFor, onError, run, t, tokenDraft, tokenLabel, username]);

  const updateTokenLabel = useCallback(
    async (tokenId: number) => {
      const label = tokenLabelDrafts[tokenId] ?? "";
      const updated = await run(
        `x-token-label-${tokenId}`,
        () => NyaApi.updateXToken(tokenId, label),
        () => t("common.saved")
      );
      if (updated) await loadTokensFor(username, false);
    },
    [loadTokensFor, run, t, tokenLabelDrafts, username]
  );

  const revokeToken = useCallback(
    async (tokenId: number) => {
      const revoked = await run(
        `x-token-revoke-${tokenId}`,
        () => NyaApi.revokeXToken(tokenId),
        () => t("admin.x.revoked")
      );
      if (revoked) {
        setSavedTokenId((current) => (current === tokenId ? null : current));
        await loadTokensFor(username, false);
      }
    },
    [loadTokensFor, run, t, username]
  );

  const buildOptions = useCallback((): XSyncOptions => ({
    x_token_id: savedTokenId ?? undefined,
    auth_token: savedTokenId ? undefined : tokenDraft.trim() || undefined,
    ct0: savedTokenId ? undefined : ct0Draft.trim() || undefined,
    storage_strategy: storageStrategy || undefined,
    limit: limit === "" ? undefined : limit,
    page_size: pageSize,
    max_pages: maxPages === "" ? undefined : maxPages,
    include_replies: includeReplies,
    media_only: mediaOnly,
    backfill,
    download_media: downloadMedia,
    download_concurrency: downloadConcurrency,
    request_delay_seconds: delay,
    rebuild_db: rebuildDb,
    generate_cache: generateCache,
    dry_run: dryRun,
  }), [
    backfill,
    ct0Draft,
    delay,
    downloadConcurrency,
    downloadMedia,
    dryRun,
    generateCache,
    includeReplies,
    limit,
    maxPages,
    mediaOnly,
    pageSize,
    rebuildDb,
    savedTokenId,
    storageStrategy,
    tokenDraft,
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
    includeReplies,
    setIncludeReplies,
    mediaOnly,
    setMediaOnly,
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
    ct0Draft,
    setCt0Draft,
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
