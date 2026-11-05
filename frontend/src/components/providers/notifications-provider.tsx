"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

const POLL_MS = 30_000;
const LIST_LIMIT = 20;

type NotificationsContextValue = {
  items: NotificationItem[];
  unread: number;
  loading: boolean;
  refresh: () => Promise<void>;
  markAllRead: () => Promise<void>;
  markRead: (ids: number[]) => Promise<void>;
};

const NotificationsContext = createContext<NotificationsContextValue | null>(null);

export function notificationHref(item: NotificationItem): string | undefined {
  return item.asset_key ? `/asset/${encodeURIComponent(item.asset_key)}` : undefined;
}

/**
 * Polls the signed-in user's notifications (paused while the tab is hidden) and pops new unread
 * ones as top-right toasts. The list itself is shown from the account menu.
 */
export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const { token, me, ready } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const seenRef = useRef<Set<number> | null>(null);
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const tRef = useRef(t);
  tRef.current = t;
  const enabled = ready && Boolean(token) && Boolean(me && me.role !== "guest" && me.user_id != null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await NyaApi.notifications();
      const latest = response.items.slice(0, LIST_LIMIT);
      setItems(latest);
      setUnread(response.unread_count);
      const seen = seenRef.current;
      if (seen === null) {
        // First load: remember what exists without popping old notifications.
        seenRef.current = new Set(response.items.map((item) => item.id));
      } else {
        const fresh = response.items.filter((item) => !seen.has(item.id) && !item.read_at);
        for (const item of response.items) seen.add(item.id);
        for (const item of fresh.slice(0, 3).reverse()) {
          toastRef.current.notify(localizedNotification(item, tRef.current), {
            title: tRef.current("admin.notifications.title"),
            href: notificationHref(item),
          });
        }
      }
    } catch {
      /* polling errors are silent; the menu shows the last known state */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setItems([]);
      setUnread(0);
      seenRef.current = null;
      return;
    }
    let timer: number | null = null;
    let stopped = false;
    const tick = async () => {
      if (stopped) return;
      if (!document.hidden) await refresh();
      if (!stopped) timer = window.setTimeout(tick, POLL_MS);
    };
    const onVisible = () => {
      if (!document.hidden) void refresh();
    };
    void tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, refresh, me?.user_id]);

  const markRead = useCallback(
    async (ids: number[]) => {
      try {
        await NyaApi.markNotificationsRead(ids);
        const now = new Date().toISOString();
        setItems((current) => current.map((item) => (ids.length === 0 || ids.includes(item.id) ? { ...item, read_at: item.read_at ?? now } : item)));
        setUnread((current) => (ids.length === 0 ? 0 : Math.max(0, current - ids.length)));
      } catch (error) {
        toastRef.current.error(error instanceof Error ? error.message : tRef.current("admin.notifications.readFailed"));
      }
    },
    []
  );

  const markAllRead = useCallback(() => markRead([]), [markRead]);

  const value = useMemo<NotificationsContextValue>(
    () => ({ items, unread, loading, refresh, markAllRead, markRead }),
    [items, unread, loading, refresh, markAllRead, markRead]
  );

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

export function useNotifications(): NotificationsContextValue {
  const ctx = useContext(NotificationsContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationsProvider");
  return ctx;
}

/** Backend messages are English sentences; map known kinds to localized text. */
export function localizedNotification(item: NotificationItem, t: (key: string, params?: Record<string, string | number>) => string): string {
  const key = `admin.notifications.kinds.${item.kind}`;
  const text = t(key);
  return text === key ? item.message : text;
}
