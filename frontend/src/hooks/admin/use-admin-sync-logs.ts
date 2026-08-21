"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import type { UploadLogItem, UploadLogResponse } from "@/lib/types";
import type { AdminPollingMode } from "./use-admin-operations";

const ACTIVE_POLL_MS = 5_000;
const IDLE_POLL_MS = 20_000;

type UseAdminSyncLogsOptions = {
  enabled: boolean;
  onError: (message: string) => void;
  loader: (limit: number) => Promise<UploadLogResponse>;
  limit?: number;
};

/** Shared polling for sync-module log feeds (Pixiv, Misskey, ...). Backs off when idle or hidden. */
export function useAdminSyncLogs({ enabled, onError, loader, limit = 40 }: UseAdminSyncLogsOptions) {
  const [logs, setLogs] = useState<UploadLogItem[]>([]);
  const [pollingMode, setPollingMode] = useState<AdminPollingMode>("idle");
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const latestLogsRef = useRef<UploadLogItem[]>([]);
  const pollNowRef = useRef<((showError?: boolean) => Promise<UploadLogItem[] | null>) | null>(null);
  const loadPromiseRef = useRef<Promise<UploadLogItem[] | null> | null>(null);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    latestLogsRef.current = logs;
  }, [logs]);

  const load = useCallback(
    async (showError = true) => {
      if (loadPromiseRef.current) return loadPromiseRef.current;

      const promise = (async () => {
        try {
          const response = await loaderRef.current(limit);
          setLogs(response.items);
          latestLogsRef.current = response.items;
          setLastUpdatedAt(new Date().toISOString());
          return response.items;
        } catch (err) {
          if (showError) onError(err instanceof ApiError ? err.message : String(err));
          return null;
        }
      })();

      loadPromiseRef.current = promise;
      try {
        return await promise;
      } finally {
        if (loadPromiseRef.current === promise) {
          loadPromiseRef.current = null;
        }
      }
    },
    [limit, onError]
  );

  const refresh = useCallback(
    async (showError = true) => {
      return pollNowRef.current ? pollNowRef.current(showError) : load(showError);
    },
    [load]
  );

  useEffect(() => {
    if (!enabled) {
      setPollingMode("paused");
      pollNowRef.current = null;
      return;
    }

    let stopped = false;
    let timer: number | null = null;

    function clearTimer() {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    }

    function scheduleNext(items: UploadLogItem[] | null | undefined) {
      if (stopped) return;
      clearTimer();
      if (document.hidden) {
        setPollingMode("paused");
        return;
      }

      const active = hasRecentSyncActivity(items ?? latestLogsRef.current);
      setPollingMode(active ? "active" : "idle");
      timer = window.setTimeout(() => void poll(false), active ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    }

    async function poll(showError = false): Promise<UploadLogItem[] | null> {
      if (stopped) return null;
      if (document.hidden) {
        scheduleNext(null);
        return null;
      }
      const items = await load(showError);
      scheduleNext(items);
      return items;
    }

    function onVisibilityChange() {
      if (document.hidden) {
        clearTimer();
        setPollingMode("paused");
      } else {
        void poll(false);
      }
    }

    pollNowRef.current = (showError = false) => {
      clearTimer();
      return poll(showError);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    void poll(false);

    return () => {
      stopped = true;
      clearTimer();
      pollNowRef.current = null;
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, load]);

  return { logs, pollingMode, lastUpdatedAt, load, refresh };
}

export function hasRecentSyncActivity(logs: UploadLogItem[]): boolean {
  const latest = logs[0];
  if (!latest?.created_at) return false;
  if (latest.status === "queued" || latest.status === "running") return true;
  const created = new Date(latest.created_at).getTime();
  if (Number.isNaN(created)) return false;
  return Date.now() - created < 60_000;
}
