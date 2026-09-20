"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRightLeft,
  AtSign,
  BadgeDollarSign,
  Database,
  Globe2,
  Hash,
  HelpCircle,
  Images,
  LayoutDashboard,
  MessageSquareText,
  Search,
  Settings,
  Settings2,
  Shield,
  Sparkles,
  Tags,
  Upload,
  UserCog,
  UsersRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { SidebarShell } from "@/components/layout/sidebar-shell";
import { TopbarShell } from "@/components/layout/topbar-shell";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { useSiteConfig } from "@/lib/hooks";
import { DEFAULT_REPOSITORY_URL, resolveBranding, resolveDefaultLayout, type LayoutStyle } from "@/lib/branding";
import {
  ADMIN_SECTION_ORDER,
  canAccessAdminSection,
  getAdminSectionHref,
  getVisibleAdminSection,
  normalizeAdminSection,
  type AdminSection,
} from "@/lib/admin-sections";
import type { ShellModel, ShellNavItem } from "@/components/layout/shell-model";

const LAYOUT_STORAGE_KEY = "nya.gallery.layout";
const SIDEBAR_STORAGE_KEY = "nya.gallery.sidebar-collapsed";
const LAYOUT_SWITCHABLE = true;

type NavDef = {
  href: string;
  icon: LucideIcon;
  labelKey: string;
  section?: AdminSection;
};

const PRIMARY_NAV: NavDef[] = [
  { href: "/", labelKey: "nav.home", icon: Sparkles },
  { href: "/files", labelKey: "nav.files", icon: Images },
  { href: "/posts", labelKey: "nav.posts", icon: MessageSquareText },
  { href: "/search", labelKey: "nav.search", icon: Search },
];

const PRIVATE_NAV: NavDef[] = [
  { href: "/upload", labelKey: "nav.upload", icon: Upload },
  { href: "/admin", labelKey: "nav.admin", icon: Settings },
];

const ADMIN_SECTION_ICONS: Record<AdminSection, LucideIcon> = {
  dashboard: LayoutDashboard,
  pixiv: Globe2,
  misskey: AtSign,
  x: Hash,
  fanbox: BadgeDollarSign,
  operations: Activity,
  security: Shield,
  tags: Tags,
  maintenance: Database,
  accounts: UserCog,
  access: UsersRound,
  migration: ArrowRightLeft,
  developer: Settings2,
};

const ADMIN_NAV: NavDef[] = ADMIN_SECTION_ORDER.map((section) => ({
  section,
  icon: ADMIN_SECTION_ICONS[section],
  href: getAdminSectionHref(section),
  labelKey: `admin.sections.${section}`,
}));

const SUPPORT_NAV: NavDef[] = [{ href: "/faq", labelKey: "nav.faq", icon: HelpCircle }];

/** Shared auth-aware navigation and shell state for both layout variants. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { token, ready, me } = useAuth();
  const { t } = useI18n();
  const { data: siteConfig } = useSiteConfig();

  const defaultLayout = resolveDefaultLayout(siteConfig);
  const branding = resolveBranding(siteConfig);
  const signedIn = ready && Boolean(token);
  const [layout, setLayout] = useState<LayoutStyle>(defaultLayout);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    setLayout(stored === "sidebar" || stored === "topbar" ? stored : defaultLayout);
  }, [defaultLayout]);

  useEffect(() => {
    setSidebarCollapsed(window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true");
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const changeLayout = (nextLayout: LayoutStyle) => {
    if (!LAYOUT_SWITCHABLE) return;
    setLayout(nextLayout);
    setMobileOpen(false);
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, nextLayout);
  };

  const changeSidebar = (nextCollapsed: boolean) => {
    setSidebarCollapsed(nextCollapsed);
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(nextCollapsed));
  };

  const requestedAdminSection = normalizeAdminSection(searchParams?.get("section"));
  const adminSection = getVisibleAdminSection(me?.role, requestedAdminSection) ?? requestedAdminSection;

  const privateItems = signedIn ? PRIVATE_NAV : [];
  const adminDefs = signedIn
    ? ADMIN_NAV.filter((item) => item.section && canAccessAdminSection(me?.role, item.section))
    : [];
  const onAdmin = isActivePath(pathname, "/admin");

  const toItem = (def: NavDef): ShellNavItem => ({
    href: def.href,
    icon: def.icon,
    label: t(def.labelKey),
    section: def.section,
    active: def.section
      ? isActiveAdminSection(pathname, adminSection, def.section)
      : isActivePath(pathname, def.href),
  });

  const groups = [
    { id: "gallery", labelKey: "layout.groups.gallery", items: PRIMARY_NAV },
    { id: "workspace", labelKey: "layout.groups.workspace", items: privateItems },
    { id: "support", labelKey: "layout.groups.support", items: SUPPORT_NAV },
  ]
    .filter((group) => group.items.length > 0)
    .map((group) => ({ id: group.id, label: t(group.labelKey), items: group.items.map(toItem) }));

  const adminItems = adminDefs.map(toItem);
  const inlinePrivateItems = adminItems.length > 0
    ? privateItems.filter((item) => item.href !== "/admin")
    : privateItems;

  const model: ShellModel = {
    branding,
    groups,
    inlineItems: [...PRIMARY_NAV, ...inlinePrivateItems, ...adminDefs, ...SUPPORT_NAV].map(toItem),
    adminItems,
    showAdminSubnav: signedIn && onAdmin && adminItems.length > 0,
    headerTitle: currentSectionLabel(pathname, adminSection, t, branding.appName),
    repositoryUrl: siteConfig?.repository || DEFAULT_REPOSITORY_URL,
    icpBeian: siteConfig?.icp_beian ?? null,
    layout,
    layoutSwitchable: LAYOUT_SWITCHABLE,
    sidebarCollapsed,
    onChangeLayout: changeLayout,
    onCollapseSidebar: changeSidebar,
    mobileOpen,
    onToggleMobile: () => setMobileOpen((value) => !value),
    onCloseMobile: () => setMobileOpen(false),
  };

  const Shell = layout === "topbar" ? TopbarShell : SidebarShell;
  return <Shell model={model}>{children}</Shell>;
}

function isActivePath(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/") return pathname === "/";
  if (href.includes("?")) return false;
  if (href === "/files" && pathname.startsWith("/asset/")) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function isActiveAdminSection(pathname: string | null, currentSection: string, section: string): boolean {
  return pathname === "/admin" && currentSection === section;
}

function currentSectionLabel(
  pathname: string | null,
  adminSection: string,
  t: (key: string) => string,
  fallback: string
): string {
  if (!pathname) return fallback;
  if (pathname === "/admin") {
    const section = ADMIN_NAV.find((item) => item.section === adminSection);
    return section ? t(section.labelKey) : t("nav.admin");
  }
  const item = [...PRIMARY_NAV, ...PRIVATE_NAV].find((nav) => isActivePath(pathname, nav.href));
  if (item) return t(item.labelKey);
  if (pathname.startsWith("/faq")) return t("nav.faq");
  return fallback;
}
