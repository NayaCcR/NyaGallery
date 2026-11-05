/**
 * Built-in colour palettes (roadmap 20.1, first step). A palette only overrides CSS variables, so it
 * cannot break layout or functionality; light / dark mode stays independent. The active palette is
 * set as `data-palette` on <html> (see globals.css) and stored in localStorage.
 */
export const PALETTE_STORAGE_KEY = "nya.palette";

export const THEME_PALETTES = [
  { id: "glacier", swatch: "hsl(191 82% 36%)" },
  { id: "sakura", swatch: "hsl(340 72% 52%)" },
  { id: "violet", swatch: "hsl(262 60% 55%)" },
  { id: "forest", swatch: "hsl(152 55% 34%)" },
  { id: "amber", swatch: "hsl(30 90% 46%)" },
  { id: "graphite", swatch: "hsl(220 10% 32%)" },
] as const;

export type ThemePaletteId = (typeof THEME_PALETTES)[number]["id"];

export const DEFAULT_PALETTE: ThemePaletteId = "glacier";

export function isThemePalette(value: string | null | undefined): value is ThemePaletteId {
  return THEME_PALETTES.some((palette) => palette.id === value);
}

/** Inline script body that applies the stored palette before first paint (no flash). */
export const PALETTE_BOOT_SCRIPT = `try{var p=localStorage.getItem('${PALETTE_STORAGE_KEY}');if(p&&/^(${THEME_PALETTES.map((p) => p.id).join("|")})$/.test(p)&&p!=='${DEFAULT_PALETTE}')document.documentElement.dataset.palette=p;}catch(e){}`;
