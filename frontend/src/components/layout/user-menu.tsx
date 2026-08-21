"use client";

import Link from "next/link";
import { useState } from "react";
import { LogIn, LogOut, User } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function UserMenu() {
  const { token, logout, ready, me } = useAuth();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

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

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="control-glow"
        aria-label={t("auth.account")}
        onClick={() => setOpen((value) => !value)}
      >
        <User className="h-4 w-4" />
      </Button>
      <div
        className={cn(
          "absolute right-0 top-full z-50 mt-1 w-48 origin-top-right rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg transition",
          open ? "animate-scale-in" : "pointer-events-none scale-95 opacity-0"
        )}
        onMouseLeave={() => setOpen(false)}
      >
        <div className="px-3 py-2 text-xs text-muted-foreground">
          {me?.auth_method === "bearer" ? t("auth.apiTokenSession") : t("auth.cookieSession")}
        </div>
        <div className="px-3 py-2 text-xs text-muted-foreground">{me?.username || t("auth.signedIn")}</div>
        <button
          type="button"
          onClick={() => {
            void logout();
            setOpen(false);
          }}
          className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm hover:bg-accent"
        >
          <LogOut className="h-4 w-4" /> {t("auth.logout")}
        </button>
      </div>
    </div>
  );
}
