"use client";

import { NyaApi } from "@/lib/api";
import { useAdminSyncLogs } from "./use-admin-sync-logs";

type UseAdminPixivLogsOptions = {
  enabled: boolean;
  onError: (message: string) => void;
};

export function useAdminPixivLogs({ enabled, onError }: UseAdminPixivLogsOptions) {
  const { logs, pollingMode, lastUpdatedAt, load, refresh } = useAdminSyncLogs({
    enabled,
    onError,
    loader: (limit) => NyaApi.pixivLogs(limit),
  });
  return {
    logs,
    pollingMode,
    lastUpdatedAt,
    loadPixivLogs: load,
    refreshPixivLogs: refresh,
  };
}
