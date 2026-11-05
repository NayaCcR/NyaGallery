"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bell, CheckCheck, LogIn, LogOut, Settings, User } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { localizedNotification, notificationHref, useNotifications } from "@/components/providers/notifications-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NotificationItem } from "@/lib/types";

export function UserMenu() {
  const { token, logout, ready, me } = useAuth();
  const { t } = useI18n();
  const { items, unread, markAllRead, markRead, refresh } = useNotifications();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside click or Escape instead of on mouse-leave, so the menu is usable.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  if (!ready) {
    return (
      <Button variant="ghost" size="icon" className="control-glow" aria-label={t("auth.account")}>
        <User className="h-4 w-4" />
      </Button>
    );
  }

  if (!token) {
    return (
      <Button asChild variant="ghost" size="sm" className="control-glow">
        <Link href="/login" className="inline-flex items-center gap-1.5">
          <LogIn className="h-4 w-4" />
          <span className="hidden sm:inline">{t("auth.login")}</span>
        </Link>
      </Button>
    );
  }

  const canManage = Boolean(me?.permissions?.includes("upload") || me?.permissions?.includes("admin"));

  return (
    <div className="relative" ref={rootRef}>
      <Button
        variant="ghost"
        size="icon"
        className="control-glow relative"
        aria-label={unread > 0 ? `${t("auth.account")} · ${t("admin.notifications.unread", { count: unread })}` : t("auth.account")}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <User className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-destructive-foreground ring-2 ring-background">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </Button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-1.5rem))] origin-top-right animate-scale-in overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-xl"
        >
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
              <User className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{me?.username || t("auth.signedIn")}</div>
              <div className="truncate text-xs text-muted-foreground">
                {me?.role} · {me?.auth_method === "bearer" ? t("auth.apiTokenSession") : t("auth.cookieSession")}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between px-4 pb-1 pt-3">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Bell className="h-3.5 w-3.5" /> {t("admin.notifications.title")}
              {unread > 0 && <span className="rounded-full bg-destructive/10 px-1.5 text-[10px] text-destructive">{unread}</span>}
            </span>
            <button
              type="button"
              disabled={unread === 0}
              onClick={() => void markAllRead()}
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-40 focus-ring"
            >
              <CheckCheck className="h-3.5 w-3.5" /> {t("admin.notifications.markAllRead")}
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto px-2 pb-2">
            {items.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-muted-foreground">{t("admin.notifications.empty")}</p>
            ) : (
              items.map((item) => (
                <NotificationRow
                  key={item.id}
                  item={item}
                  onOpen={() => {
                    if (!item.read_at) void markRead([item.id]);
                    setOpen(false);
                  }}
                />
              ))
            )}
          </div>

          <div className="border-t border-border p-1">
            {canManage && (
              <Link
                href="/admin"
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm hover:bg-accent"
              >
                <Settings className="h-4 w-4" /> {t("admin.notifications.openAdmin")}
              </Link>
            )}
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                void logout();
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-destructive hover:bg-destructive/10"
            >
              <LogOut className="h-4 w-4" /> {t("auth.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function NotificationRow({ item, onOpen }: { item: NotificationItem; onOpen: () => void }) {
  const { t } = useI18n();
  const href = notificationHref(item);
  const content = (
    <>
      <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", item.read_at ? "bg-transparent" : "bg-primary")} />
      <span className="min-w-0 flex-1">
        <span className={cn("block text-sm leading-5", !item.read_at && "font-medium")}>{localizedNotification(item, t)}</span>
        <span className="mt-0.5 block text-[11px] text-muted-foreground">{formatRelative(item.created_at)}</span>
      </span>
    </>
  );
  const className = cn("flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left hover:bg-muted", !item.read_at && "bg-primary/5");
  return href ? (
    <Link href={href} onClick={onOpen} className={className} role="menuitem">
      {content}
    </Link>
  ) : (
    <button type="button" onClick={onOpen} className={className} role="menuitem">
      {content}
    </button>
  );
}

function formatRelative(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diff = (Date.now() - date.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (diff < 60) return rtf.format(-Math.round(diff), "second");
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), "minute");
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), "hour");
  if (diff < 86400 * 7) return rtf.format(-Math.round(diff / 86400), "day");
  return date.toLocaleDateString();
}
