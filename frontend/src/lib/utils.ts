import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

export function tagCategory(tag: string): string {
  const idx = tag.indexOf(":");
  return idx > 0 ? tag.slice(0, idx) : "general";
}

export function tagLabel(
  tag: string,
  labels?: Record<string, string> | null,
  locale = "zh-CN",
  defaultLocale = "zh-CN",
): string {
  const localized = labels?.[locale] || labels?.[defaultLocale];
  if (localized) return localized;
  const idx = tag.indexOf(":");
  const body = idx > 0 ? tag.slice(idx + 1) : tag;
  return body.replace(/_/g, " ");
}

export function tagBody(tag: string): string {
  const idx = tag.indexOf(":");
  return idx > 0 ? tag.slice(idx + 1) : tag;
}

export function sourceTagQuery(name: string, translatedName?: string | null): string {
  const basis = translatedName?.trim() || name.trim();
  return `source_tag:${canonicalTagBody(basis)}`;
}

export function sourceTagLabel(
  name: string,
  translatedName?: string | null,
  locale = "zh-CN",
): string {
  const raw = name.trim();
  const translated = translatedName?.trim() || "";
  if (locale.toLowerCase().startsWith("en")) {
    return translated || raw;
  }
  return raw || translated;
}

export function sourceTagSecondaryLabel(
  name: string,
  translatedName?: string | null,
  locale = "zh-CN",
): string | null {
  const raw = name.trim();
  const translated = translatedName?.trim() || "";
  const primary = sourceTagLabel(name, translatedName, locale);
  const secondary = locale.toLowerCase().startsWith("en") ? raw : translated;
  return secondary && secondary !== primary ? secondary : null;
}

export function isVideoMedia(mimeType?: string | null): boolean {
  return (mimeType ?? "").toLowerCase().startsWith("video/");
}

export function formatDateTime(value: string | null | undefined, locale?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}

/** X delivers GIFs as silent mp4s; they should loop like an image, not sit behind a play button. */
export function isAnimatedGifMedia(sourceType?: string | null): boolean {
  return (sourceType ?? "").toLowerCase() === "animated_gif";
}

export function isHiddenTag(tag: string): boolean {
  const normalized = tag.trim().toLowerCase();
  const idx = normalized.indexOf(":");
  const category = idx > 0 ? normalized.slice(0, idx) : "general";
  const body = idx > 0 ? normalized.slice(idx + 1) : normalized;
  return category === "meta" && (
    body === "hide" ||
    body.startsWith("hide_") ||
    body.startsWith("hide-")
  );
}

export function isTechnicalTag(tag: string): boolean {
  const body = tagBody(tag);
  if (body.startsWith("aspect_")) return true;
  return body === "landscape" || body === "portrait" || body === "square" || body === "unusual_aspect";
}

export function categoryColor(category: string): string {
  const palette: Record<string, string> = {
    artist: "text-amber-500 border-amber-500/30 bg-amber-500/10",
    uploader: "text-amber-500 border-amber-500/30 bg-amber-500/10",
    source: "text-teal-500 border-teal-500/30 bg-teal-500/10",
    character: "text-emerald-500 border-emerald-500/30 bg-emerald-500/10",
    series: "text-sky-500 border-sky-500/30 bg-sky-500/10",
    type: "text-fuchsia-500 border-fuchsia-500/30 bg-fuchsia-500/10",
    clothing: "text-pink-500 border-pink-500/30 bg-pink-500/10",
    source_tag: "text-cyan-500 border-cyan-500/30 bg-cyan-500/10",
    rating: "text-red-500 border-red-500/30 bg-red-500/10",
    date: "text-slate-500 border-slate-500/30 bg-slate-500/10",
    meta: "text-violet-500 border-violet-500/30 bg-violet-500/10",
    general: "text-muted-foreground border-border bg-muted",
  };
  return palette[category] ?? palette.general;
}

function canonicalTagBody(value: string): string {
  return value
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\p{Mark}_.+-]+/gu, "_")
    .replace(/^[._-]+|[._-]+$/g, "");
}
