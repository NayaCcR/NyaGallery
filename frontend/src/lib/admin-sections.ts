import type { Role } from "@/lib/types";

export type AdminSection =
  | "dashboard"
  | "pixiv"
  | "misskey"
  | "x"
  | "fanbox"
  | "operations"
  | "security"
  | "tags"
  | "maintenance"
  | "accounts"
  | "developer";

export const ADMIN_SECTION_ORDER: AdminSection[] = [
  "dashboard",
  "pixiv",
  "misskey",
  "x",
  "fanbox",
  "operations",
  "security",
  "tags",
  "maintenance",
  "accounts",
  "developer",
];

const ADMIN_SECTION_ROLES: Record<AdminSection, Role[]> = {
  dashboard: ["viewer", "editor", "admin", "developer"],
  pixiv: ["editor", "admin", "developer"],
  misskey: ["editor", "admin", "developer"],
  x: ["editor", "admin", "developer"],
  fanbox: ["editor", "admin", "developer"],
  operations: ["viewer", "editor", "admin", "developer"],
  security: ["admin", "developer"],
  tags: ["admin", "developer"],
  maintenance: ["admin", "developer"],
  accounts: ["viewer", "editor", "admin", "developer"],
  developer: ["developer"],
};

export function normalizeAdminSection(value: string | null | undefined): AdminSection {
  return isAdminSection(value) ? value : "dashboard";
}

export function canAccessAdminSection(role: Role | null | undefined, section: AdminSection): boolean {
  if (!role || role === "guest") return false;
  return ADMIN_SECTION_ROLES[section].includes(role);
}

export function getAdminSectionsForRole(role: Role | null | undefined): AdminSection[] {
  return ADMIN_SECTION_ORDER.filter((section) => canAccessAdminSection(role, section));
}

export function getDefaultAdminSection(role: Role | null | undefined): AdminSection | null {
  return getAdminSectionsForRole(role)[0] ?? null;
}

export function getVisibleAdminSection(
  role: Role | null | undefined,
  requested: AdminSection
): AdminSection | null {
  return canAccessAdminSection(role, requested) ? requested : getDefaultAdminSection(role);
}

export function getAdminSectionHref(section: AdminSection): string {
  return section === "dashboard" ? "/admin" : `/admin?section=${section}`;
}

function isAdminSection(value: string | null | undefined): value is AdminSection {
  return Boolean(value && (ADMIN_SECTION_ORDER as string[]).includes(value));
}
