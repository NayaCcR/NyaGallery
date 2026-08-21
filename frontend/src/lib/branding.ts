import type { SiteConfigResponse } from "@/lib/types";

/**
 * Compile-time branding defaults. Anything the backend returns from
 * /api/site/config overrides these at runtime, so a deployment can rebrand
 * without rebuilding. See FrontTemplate/README.md for the reusable version.
 */

export type LayoutStyle = "sidebar" | "topbar";

export type Branding = {
  appName: string;
  logoUrl: string;
  logoFallbackText: string;
  logoSize: { sidebar: number; topbar: number };
};

export const BRANDING_DEFAULTS: Branding = {
  appName: "NyaGallery",
  logoUrl: "/logo.png",
  logoFallbackText: "N",
  logoSize: { sidebar: 36, topbar: 32 },
};

export const DEFAULT_LAYOUT: LayoutStyle = "sidebar";
export const DEFAULT_REPOSITORY_URL = "https://github.com/NayaCcR/NyaGallery";

export function resolveBranding(config?: SiteConfigResponse | null): Branding {
  return {
    ...BRANDING_DEFAULTS,
    appName: trimmed(config?.app_name) ?? BRANDING_DEFAULTS.appName,
    logoUrl: config?.logo_url === "" ? "" : trimmed(config?.logo_url) ?? BRANDING_DEFAULTS.logoUrl,
  };
}

export function resolveDefaultLayout(config?: SiteConfigResponse | null): LayoutStyle {
  return isLayoutStyle(config?.layout) ? config.layout : DEFAULT_LAYOUT;
}

export function isLayoutStyle(value: unknown): value is LayoutStyle {
  return value === "sidebar" || value === "topbar";
}

function trimmed(value: string | null | undefined): string | null {
  const text = (value ?? "").trim();
  return text || null;
}
