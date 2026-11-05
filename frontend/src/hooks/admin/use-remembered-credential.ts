"use client";

import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";

type CredentialLike = { id: number; is_active: boolean };

const STORAGE_PREFIX = "nya.admin.credential.";
const NONE = "none";

function readStored(key: string): number | typeof NONE | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + key);
    if (raw === NONE) return NONE;
    const value = raw ? Number(raw) : NaN;
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, value: number | typeof NONE | null) {
  try {
    if (value == null) window.localStorage.removeItem(STORAGE_PREFIX + key);
    else window.localStorage.setItem(STORAGE_PREFIX + key, String(value));
  } catch {
    /* storage unavailable (private mode); the selection still works for this page view */
  }
}

/**
 * Selected saved-credential id that survives reloads. Only the numeric id is stored locally,
 * never the secret. When the credential list first loads, a remembered id is restored if it is
 * still active; otherwise a single active credential is picked automatically. An explicit
 * "none" choice by the user is remembered and respected.
 */
export function useRememberedCredential(storageKey: string, items: CredentialLike[], loaded: boolean) {
  const [selectedId, setSelectedIdState] = useState<number | null>(null);
  const restoredRef = useRef(false);

  const setSelectedId = useCallback(
    (value: SetStateAction<number | null>) => {
      setSelectedIdState((current) => {
        const next = typeof value === "function" ? value(current) : value;
        writeStored(storageKey, next ?? NONE);
        return next;
      });
    },
    [storageKey]
  );

  useEffect(() => {
    if (!loaded || restoredRef.current) return;
    restoredRef.current = true;
    const active = items.filter((item) => item.is_active);
    const stored = readStored(storageKey);
    setSelectedIdState((current) => {
      if (current != null) return current;
      if (typeof stored === "number" && active.some((item) => item.id === stored)) return stored;
      if (stored !== NONE && active.length === 1) return active[0].id;
      return null;
    });
  }, [items, loaded, storageKey]);

  // Forget a selection whose credential was revoked or deleted.
  useEffect(() => {
    if (!loaded || selectedId == null) return;
    if (!items.some((item) => item.id === selectedId && item.is_active)) {
      setSelectedIdState(null);
      writeStored(storageKey, null);
    }
  }, [items, loaded, selectedId, storageKey]);

  return [selectedId, setSelectedId] as const;
}
