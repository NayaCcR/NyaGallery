"use client";

import { useEffect, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

export function AdminNotificationsPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const response = await NyaApi.notifications();
      setItems(response.items);
      setUnread(response.unread_count);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("admin.notifications.loadFailed"));
    }
  }

  useEffect(() => { void load(); }, []);

  async function markRead() {
    setBusy(true);
    try {
      await NyaApi.markNotificationsRead();
      await load();
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.notifications.readFailed")); }
    finally { setBusy(false); }
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-medium"><Bell className="h-4 w-4" /> {t("admin.notifications.title")}{unread > 0 ? ` (${unread})` : ""}</h2>
        <Button variant="outline" size="sm" onClick={markRead} disabled={busy || unread === 0}><CheckCheck className="mr-2 h-4 w-4" />{t("admin.notifications.markAllRead")}</Button>
      </div>
      {items.length === 0 ? <p className="text-xs text-muted-foreground">{t("admin.notifications.empty")}</p> : <div className="divide-y divide-border rounded-md border border-border">{items.map((item) => <div key={item.id} className={`p-3 text-sm ${item.read_at ? "" : "bg-muted/30"}`}><div className="font-medium">{item.message}</div><div className="mt-1 text-xs text-muted-foreground">{item.kind} · {new Date(item.created_at).toLocaleString()}</div></div>)}</div>}
    </section>
  );
}
