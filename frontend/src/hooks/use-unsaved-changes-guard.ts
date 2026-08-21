"use client";

import { useCallback, useEffect } from "react";

type UnsavedChangesGuardOptions = {
  dirty: boolean;
  message: string;
  onDiscard?: () => void;
};

/** Warn before a draft is discarded by an in-app link, reload, or tab close. */
export function useUnsavedChangesGuard({ dirty, message, onDiscard }: UnsavedChangesGuardOptions) {
  const confirmDiscard = useCallback(() => {
    if (!dirty) return true;
    if (!window.confirm(message)) return false;
    onDiscard?.();
    return true;
  }, [dirty, message, onDiscard]);

  useEffect(() => {
    if (!dirty) return undefined;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return undefined;
    const handleLinkClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (!(event.target instanceof Element)) return;
      const anchor = event.target.closest<HTMLAnchorElement>("a[href]");
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;

      const current = new URL(window.location.href);
      const destination = new URL(anchor.href, current);
      if (destination.href === current.href) return;
      if (confirmDiscard()) return;

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    };
    document.addEventListener("click", handleLinkClick, true);
    return () => document.removeEventListener("click", handleLinkClick, true);
  }, [confirmDiscard, dirty]);

  return confirmDiscard;
}
