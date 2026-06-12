"use client";

import { useCallback, useState } from "react";
import { ApiError, NyaApi } from "@/lib/api";
import type { PixivConfigResponse } from "@/lib/types";

type UseAdminPixivSettingsOptions = {
  onError: (message: string) => void;
};

export function useAdminPixivSettings({ onError }: UseAdminPixivSettingsOptions) {
  const [pixivLimit, setPixivLimit] = useState(20);
  const [pixivRebuildDb, setPixivRebuildDb] = useState(true);
  const [pixivGenerateCache, setPixivGenerateCache] = useState(false);
  const [pixivDryRun, setPixivDryRun] = useState(false);
  const [pixivPublicFirst, setPixivPublicFirst] = useState(true);
  const [pixivDelay, setPixivDelay] = useState(1);
  const [pixivMaxRetries, setPixivMaxRetries] = useState(3);
  const [pixivRetryBase, setPixivRetryBase] = useState(60);
  const [pixivRetryMax, setPixivRetryMax] = useState(300);
  const [pixivConcurrency, setPixivConcurrency] = useState(1);
  const [pixivStorageStrategy, setPixivStorageStrategy] = useState("local");
  const [pixivConfig, setPixivConfig] = useState<PixivConfigResponse | null>(null);

  const loadPixivConfig = useCallback(async () => {
    try {
      const config = await NyaApi.pixivConfig();
      setPixivConfig(config);
      setPixivDelay(config.default_request_delay_seconds ?? 1);
      setPixivConcurrency(Math.min(1, config.max_concurrency ?? 1));
      setPixivStorageStrategy((current) => (
        config.storage_strategies?.some((strategy) => strategy.name === current)
          ? current
          : config.default_storage_strategy || config.storage_strategies?.[0]?.name || "local"
      ));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
    }
  }, [onError]);

  return {
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
  };
}
