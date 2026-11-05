"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { DEFAULT_PALETTE, PALETTE_STORAGE_KEY, isThemePalette, type ThemePaletteId } from "@/lib/theme-palettes";

export type Theme = "light" | "dark" | "system";

type ThemeContextValue = {
  theme: Theme;
  resolved: "light" | "dark";
  palette: ThemePaletteId;
  setTheme: (theme: Theme) => void;
  setPalette: (palette: ThemePaletteId) => void;
  toggle: () => void;
};

const STORAGE_KEY = "nya.theme";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: Theme): "light" | "dark" {
  const prefersDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved: "light" | "dark" =
    theme === "dark" || (theme === "system" && prefersDark) ? "dark" : "light";
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", resolved === "dark");
  }
  return resolved;
}

function applyPalette(palette: ThemePaletteId) {
  if (typeof document === "undefined") return;
  if (palette === DEFAULT_PALETTE) delete document.documentElement.dataset.palette;
  else document.documentElement.dataset.palette = palette;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolved, setResolved] = useState<"light" | "dark">("light");
  const [palette, setPaletteState] = useState<ThemePaletteId>(DEFAULT_PALETTE);

  useEffect(() => {
    const stored = (typeof window !== "undefined"
      ? (localStorage.getItem(STORAGE_KEY) as Theme | null)
      : null) ?? "system";
    setThemeState(stored);
    setResolved(applyTheme(stored));
    try {
      const storedPalette = localStorage.getItem(PALETTE_STORAGE_KEY);
      const next = isThemePalette(storedPalette) ? storedPalette : DEFAULT_PALETTE;
      setPaletteState(next);
      applyPalette(next);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => setResolved(applyTheme("system"));
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    setResolved(applyTheme(next));
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const setPalette = useCallback((next: ThemePaletteId) => {
    setPaletteState(next);
    applyPalette(next);
    try {
      localStorage.setItem(PALETTE_STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme(resolved === "dark" ? "light" : "dark");
  }, [resolved, setTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolved, palette, setTheme, setPalette, toggle }),
    [theme, resolved, palette, setTheme, setPalette, toggle]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
