"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { Bell, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastVariant = "default" | "success" | "error" | "notification";

type Toast = {
  id: number;
  message: string;
  variant: ToastVariant;
  title?: string;
  href?: string;
};

type ToastOptions = { title?: string; href?: string; durationMs?: number };

type ToastContextValue = {
  push: (message: string, variant?: ToastVariant, options?: ToastOptions) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  notify: (message: string, options?: ToastOptions) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);
const MAX_VISIBLE = 4;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (message: string, variant: ToastVariant = "default", options: ToastOptions = {}) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((prev) => [...prev, { id, message, variant, title: options.title, href: options.href }].slice(-MAX_VISIBLE));
      const duration = options.durationMs ?? (variant === "error" ? 6000 : variant === "notification" ? 8000 : 3500);
      window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss]
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (message: string) => push(message, "success"),
      error: (message: string) => push(message, "error"),
      notify: (message: string, options?: ToastOptions) => push(message, "notification", options),
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* Top-right stack below the 64px header so it never covers the header controls. */}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-3 top-[4.5rem] z-50 flex w-[min(22rem,calc(100vw-1.5rem))] flex-col items-stretch gap-2 sm:right-4"
      >
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const Icon = toast.variant === "success" ? CheckCircle2 : toast.variant === "error" ? XCircle : toast.variant === "notification" ? Bell : Info;
  const body = (
    <div className="flex min-w-0 flex-1 items-start gap-2.5">
      <Icon
        className={cn(
          "mt-0.5 h-4 w-4 shrink-0",
          toast.variant === "success" && "text-emerald-500",
          toast.variant === "error" && "text-destructive",
          toast.variant === "notification" && "text-primary",
          toast.variant === "default" && "text-muted-foreground"
        )}
      />
      <div className="min-w-0 flex-1">
        {toast.title && <div className="truncate text-xs font-medium text-muted-foreground">{toast.title}</div>}
        <div className="break-words text-sm leading-5">{toast.message}</div>
      </div>
    </div>
  );
  return (
    <div
      role={toast.variant === "error" ? "alert" : "status"}
      className={cn(
        "pointer-events-auto flex animate-scale-in items-start gap-2 rounded-lg border bg-card/95 px-3 py-2.5 text-card-foreground shadow-lg backdrop-blur",
        toast.variant === "success" && "border-emerald-500/40",
        toast.variant === "error" && "border-destructive/45",
        toast.variant === "notification" && "border-primary/40",
        toast.variant === "default" && "border-border"
      )}
    >
      {toast.href ? (
        <Link href={toast.href} onClick={onDismiss} className="flex min-w-0 flex-1 hover:opacity-90">
          {body}
        </Link>
      ) : (
        body
      )}
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-mr-1 grid h-6 w-6 shrink-0 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground focus-ring"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
