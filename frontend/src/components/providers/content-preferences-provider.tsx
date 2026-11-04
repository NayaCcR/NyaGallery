"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "./auth-provider";
import { NyaApi } from "@/lib/api";

const STORAGE_PREFIX = "nya.content_filters";
const SENSITIVE_TAGS = ["rating:r18", "rating:r18g"] as const;
const AI_TAG = "meta:ai_generated";

type ContentPreferences = {
  showSensitive: boolean;
  showAi: boolean;
  fitMode: "fit" | "fill";
};

type ContentPreferencesContextValue = ContentPreferences & {
  ready: boolean;
  canViewSensitiveContent: boolean;
  setShowSensitive: (enabled: boolean) => void;
  setShowAi: (enabled: boolean) => void;
  fitMode: "fit" | "fill";
  setFitMode: (mode: "fit" | "fill") => void;
  applyContentFilters: (query: string | string[]) => string;
};

const DEFAULT_PREFERENCES: ContentPreferences = {
  showSensitive: false,
  showAi: false,
  fitMode: "fill",
};

const REQUIRED_ALIASES: Record<string, string[]> = {
  "rating:r18": ["rating:r18", "r18", "r-18"],
  "rating:r18g": ["rating:r18g", "r18g", "r-18g"],
  [AI_TAG]: [AI_TAG, "ai", "ai_generated"],
};

const ContentPreferencesContext = createContext<ContentPreferencesContextValue | null>(null);

export function ContentPreferencesProvider({ children }: { children: React.ReactNode }) {
  const { ready: authReady, me } = useAuth();
  const username = me?.username || "guest";
  const identityKey = `${me?.user_id ?? "guest"}:${username}:${me?.role ?? "guest"}`;
  const storageKey = `${STORAGE_PREFIX}:${username}`;
  const canViewSensitiveContent = Boolean(me && me.role !== "guest");
  const [preferences, setPreferences] = useState<ContentPreferences>(DEFAULT_PREFERENCES);
  const [ready, setReady] = useState(false);
  const [remoteLoaded, setRemoteLoaded] = useState(false);
  const previousIdentityRef = useRef<string | null>(null);

  useEffect(() => {
    if (!authReady) return;
    setReady(false);
    setRemoteLoaded(false);
    const saved = readPreferences(storageKey);
    const previousIdentity = previousIdentityRef.current;
    const identityChanged = previousIdentity !== null && previousIdentity !== identityKey;
    previousIdentityRef.current = identityKey;
    setPreferences({
      ...saved,
      showSensitive: identityChanged ? false : saved.showSensitive,
      fitMode: saved.fitMode,
    });
    setReady(true);
    if (me) {
      void NyaApi.userPreferences().then((remote) => {
        setPreferences((current) => ({ ...current, fitMode: remote.fit_mode, showSensitive: remote.show_sensitive, showAi: remote.show_ai }));
      }).catch(() => undefined).finally(() => setRemoteLoaded(true));
    } else {
      setRemoteLoaded(true);
    }
  }, [authReady, identityKey, me, storageKey]);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(preferences));
    } catch {
      /* ignore */
    }
  }, [preferences, ready, storageKey]);

  useEffect(() => {
    if (!ready || !remoteLoaded || !me) return;
    void NyaApi.updateUserPreferences({ fit_mode: preferences.fitMode, show_sensitive: preferences.showSensitive, show_ai: preferences.showAi }).catch(() => undefined);
  }, [me, preferences.fitMode, preferences.showAi, preferences.showSensitive, ready, remoteLoaded]);

  const setShowSensitive = useCallback((enabled: boolean) => {
    setPreferences((current) => ({ ...current, showSensitive: canViewSensitiveContent ? enabled : false }));
  }, [canViewSensitiveContent]);

  const setShowAi = useCallback((enabled: boolean) => {
    setPreferences((current) => ({ ...current, showAi: enabled }));
  }, []);

  const setFitMode = useCallback((mode: "fit" | "fill") => {
    setPreferences((current) => ({ ...current, fitMode: mode }));
  }, []);

  const applyContentFilters = useCallback(
    (query: string | string[]) => {
      const parts = Array.isArray(query) ? query.filter(Boolean) : splitQuery(query);
      const next = [...parts];

      if (!canViewSensitiveContent) {
        for (const tag of SENSITIVE_TAGS) {
          addForcedExclusion(next, tag);
        }
      } else if (!preferences.showSensitive) {
        for (const tag of SENSITIVE_TAGS) {
          addExclusionUnlessExplicit(next, tag);
        }
      }
      if (!preferences.showAi) {
        addExclusionUnlessExplicit(next, AI_TAG);
      }

      return Array.from(new Set(next)).join(" ");
    },
    [canViewSensitiveContent, preferences.showAi, preferences.showSensitive]
  );

  const value = useMemo<ContentPreferencesContextValue>(
    () => ({
      ...preferences,
      ready,
      canViewSensitiveContent,
      setShowSensitive,
      setShowAi,
      fitMode: preferences.fitMode,
      setFitMode,
      applyContentFilters,
    }),
    [applyContentFilters, canViewSensitiveContent, preferences, ready, setFitMode, setShowAi, setShowSensitive]
  );

  return (
    <ContentPreferencesContext.Provider value={value}>
      {children}
    </ContentPreferencesContext.Provider>
  );
}

export function useContentPreferences(): ContentPreferencesContextValue {
  const ctx = useContext(ContentPreferencesContext);
  if (!ctx) throw new Error("useContentPreferences must be used within ContentPreferencesProvider");
  return ctx;
}

function readPreferences(storageKey: string): ContentPreferences {
  try {
    const stored = localStorage.getItem(storageKey);
    if (!stored) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(stored) as Partial<ContentPreferences>;
    return {
      showSensitive: Boolean(parsed.showSensitive),
      showAi: Boolean(parsed.showAi),
      fitMode: parsed.fitMode === "fit" ? "fit" : "fill",
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function splitQuery(query: string): string[] {
  return query.trim().split(/\s+/).filter(Boolean);
}

function addExclusionUnlessExplicit(parts: string[], tag: string): void {
  if (parts.some((part) => isRequiredMatch(part, tag))) return;
  const excluded = `-${tag}`;
  if (!parts.includes(excluded)) parts.push(excluded);
}

function addForcedExclusion(parts: string[], tag: string): void {
  for (let index = parts.length - 1; index >= 0; index--) {
    if (isRequiredMatch(parts[index], tag)) parts.splice(index, 1);
  }
  const excluded = `-${tag}`;
  if (!parts.includes(excluded)) parts.push(excluded);
}

function isRequiredMatch(part: string, tag: string): boolean {
  if (!part || part.startsWith("-")) return false;
  const normalized = normalizeToken(part);
  return (REQUIRED_ALIASES[tag] ?? [tag]).some((alias) => normalizeToken(alias) === normalized);
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}
