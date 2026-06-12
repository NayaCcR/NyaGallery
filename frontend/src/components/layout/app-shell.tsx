"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Activity,
  Database,
  Github,
  Globe2,
  HelpCircle,
  Images,
  LayoutDashboard,
  Search,
  Settings,
  Settings2,
  Shield,
  Sparkles,
  Tags,
  Upload,
  UserCog,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { LanguageSelect } from "@/components/layout/language-select";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { useSiteConfig } from "@/lib/hooks";
import {
  ADMIN_SECTION_ORDER,
  canAccessAdminSection,
  getAdminSectionHref,
  getAdminSectionLabel,
  getVisibleAdminSection,
  normalizeAdminSection,
  type AdminSection,
} from "@/lib/admin-sections";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  icon: LucideIcon;
  label?: string;
  labelKey?: string;
  section?: AdminSection;
};

type AdminNavItem = NavItem & { section: AdminSection };

const PRIMARY_NAV: NavItem[] = [
  { href: "/", labelKey: "nav.home", icon: Sparkles },
  { href: "/files", labelKey: "nav.files", icon: Images },
  { href: "/search", labelKey: "nav.search", icon: Search },
];

const PRIVATE_NAV: NavItem[] = [
  { href: "/upload", labelKey: "nav.upload", icon: Upload },
  { href: "/admin", labelKey: "nav.admin", icon: Settings },
];

const ADMIN_SECTION_ICONS: Record<AdminSection, LucideIcon> = {
  dashboard: LayoutDashboard,
  pixiv: Globe2,
  operations: Activity,
  security: Shield,
  tags: Tags,
  maintenance: Database,
  accounts: UserCog,
  developer: Settings2,
};

const ADMIN_NAV: NavItem[] = ADMIN_SECTION_ORDER.map((section) => ({
  section,
  icon: ADMIN_SECTION_ICONS[section],
  href: getAdminSectionHref(section),
  label: getAdminSectionLabel(section),
}));

const SUPPORT_NAV: NavItem[] = [
  { href: "/faq", label: "FAQ", icon: HelpCircle },
];

const IMAGEFLOW_URL = "https://github.com/Yuri-NagaSaki/ImageFlow";
const SZURU_URL = "https://github.com/rr-/szurubooru";
const DEFAULT_REPOSITORY_URL = "https://github.com/NayaCcR/NyaGallery";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { token, ready, me } = useAuth();
  const { t } = useI18n();
  const { data: siteConfig } = useSiteConfig();
  const projectHomepage = siteConfig?.project_homepage || DEFAULT_REPOSITORY_URL;
  const repositoryUrl = siteConfig?.repository || DEFAULT_REPOSITORY_URL;
  const privateItems = ready && token ? PRIVATE_NAV : [];
  const requestedAdminSection = normalizeAdminSection(searchParams?.get("section"));
  const adminSection = getVisibleAdminSection(me?.role, requestedAdminSection) ?? requestedAdminSection;
  const adminItems = ready && token
    ? ADMIN_NAV.filter((item): item is AdminNavItem =>
        Boolean(item.section && canAccessAdminSection(me?.role, item.section))
      )
    : [];
  const mobilePrivateItems = adminItems.length > 0
    ? privateItems.filter((item) => item.href !== "/admin")
    : privateItems;
  const navGroups = [
    { label: "Gallery", items: PRIMARY_NAV },
    { label: "Workspace", items: privateItems },
    { label: "Support", items: SUPPORT_NAV },
  ].filter((group) => group.items.length > 0);

  return (
    <div className="min-h-screen bg-muted/25 text-foreground">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-border bg-background lg:flex lg:flex-col">
        <div className="border-b border-border px-5 py-5">
          <Link href="/" className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
              N
            </span>
            <span className="min-w-0">
              <span className="block text-lg font-semibold tracking-wide text-primary">NyaGallery</span>
              <span className="block text-[11px] uppercase text-muted-foreground">console</span>
            </span>
          </Link>
          <div className="mt-4 flex items-center justify-center gap-2 rounded-md border border-border bg-muted/35 p-2">
            <ThemeToggle />
            <LanguageSelect />
            <UserMenu />
          </div>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
          {navGroups.map((group) => (
            <div key={group.label} className="space-y-1">
              <div className="px-3 text-[11px] font-medium uppercase text-muted-foreground">{group.label}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  active={isActivePath(pathname, item.href)}
                  icon={item.icon}
                  label={item.labelKey ? t(item.labelKey) : item.label ?? ""}
                />
              ))}
              {group.label === "Workspace" && ready && token && isActivePath(pathname, "/admin") && (
                <div className="ml-4 mt-1 space-y-1 border-l border-border pl-2">
                  {adminItems.map((item) => (
                    <NavLink
                      key={item.href}
                      href={item.href}
                      active={isActiveAdminSection(pathname, adminSection, item.section)}
                      icon={item.icon}
                      label={item.label ?? ""}
                      nested
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex min-h-screen flex-col lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur">
          <div className="relative flex h-14 items-center gap-2 px-3 lg:justify-center lg:px-5">
            <Link href="/" className="flex items-center gap-2 font-semibold text-primary lg:hidden">
              <span className="grid h-8 w-8 place-items-center rounded-md bg-primary text-sm text-primary-foreground">
                N
              </span>
              <span>NyaGallery</span>
            </Link>
            <div className="hidden min-w-0 items-center gap-3 text-center lg:flex">
              <span className="grid h-8 w-8 place-items-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">
                N
              </span>
              <span>
                <span className="block text-sm font-medium leading-5">{currentSectionLabel(pathname, adminSection, t)}</span>
                <span className="block text-[11px] text-muted-foreground">NyaGallery workspace</span>
              </span>
            </div>
            <div className="ml-auto flex items-center gap-1 lg:absolute lg:right-5 lg:hidden">
              <ThemeToggle />
              <LanguageSelect />
              <UserMenu />
            </div>
          </div>
          <nav className="scrollbar-none flex gap-1 overflow-x-auto border-t border-border px-2 py-2 lg:hidden">
            {[...PRIMARY_NAV, ...mobilePrivateItems, ...adminItems, ...SUPPORT_NAV].map((item) => (
              <MobileNavLink
                key={item.href}
                href={item.href}
                active={item.section ? isActiveAdminSection(pathname, adminSection, item.section) : isActivePath(pathname, item.href)}
                icon={item.icon}
                label={item.labelKey ? t(item.labelKey) : item.label ?? ""}
              />
            ))}
          </nav>
        </header>

        <main className="flex-1 bg-background lg:rounded-l-xl lg:border-l lg:border-border">
          {children}
        </main>
        <footer className="border-t border-border bg-background px-4 py-5 text-xs text-muted-foreground lg:border-l">
          <div className="mx-auto grid w-full max-w-6xl gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-center">
            <div className="flex flex-wrap items-center justify-center gap-2 md:justify-start">
              <span>{"\uD83D\uDC3E Powered by"}</span>
              <FooterLink href={projectHomepage} className="font-medium text-foreground">
                NyaGallery
              </FooterLink>
              <span>By NayaCcR</span>
              <FooterIconLink href={repositoryUrl} label="NyaGallery GitHub repository">
                <Github className="h-4 w-4" />
              </FooterIconLink>
            </div>

            <div className="min-h-5 text-center">
              {siteConfig?.icp_beian && (
                <a
                  href="http://beian.miit.gov.cn"
                  rel="external nofollow"
                  target="_blank"
                  className="underline-offset-4 transition-colors hover:text-foreground hover:underline"
                >
                  {siteConfig.icp_beian}
                </a>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2 md:justify-end">
              <FooterCredit href={IMAGEFLOW_URL} prefix={"\u2728"} note="Inspired by">
                ImageFlow
              </FooterCredit>
              <FooterCredit href={SZURU_URL} prefix={"\u2764\uFE0F"} note="Thanks to">
                Szurubooru
              </FooterCredit>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}

function FooterLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn("underline-offset-4 transition-colors hover:text-foreground hover:underline", className)}
    >
      {children}
    </a>
  );
}

function FooterIconLink({ href, label, children }: { href: string; label: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      className="grid h-7 w-7 place-items-center rounded-md border border-border bg-muted/35 text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
    >
      {children}
    </a>
  );
}

function FooterCredit({
  href,
  prefix,
  note,
  children,
}: {
  href: string;
  prefix: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-muted/30 px-2.5 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
    >
      <span aria-hidden="true">{prefix}</span>
      <span>{note}</span>
      <span className="font-medium text-foreground">{children}</span>
    </a>
  );
}

function NavLink({
  href,
  active,
  icon: Icon,
  label,
  nested = false,
}: {
  href: string;
  active: boolean;
  icon: LucideIcon;
  label: string;
  nested?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        nested && "h-9 text-xs",
        active && "bg-primary/10 text-primary"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
    </Link>
  );
}

function MobileNavLink({
  href,
  active,
  icon: Icon,
  label,
}: {
  href: string;
  active: boolean;
  icon: LucideIcon;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground",
        active ? "bg-primary/10 text-primary" : "bg-muted/60"
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </Link>
  );
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

function currentSectionLabel(pathname: string | null, adminSection: string, t: (key: string) => string): string {
  if (!pathname) return "NyaGallery";
  if (pathname === "/admin") {
    return ADMIN_NAV.find((item) => item.section === adminSection)?.label ?? t("nav.admin");
  }
  const item = [...PRIMARY_NAV, ...PRIVATE_NAV].find((nav) => isActivePath(pathname, nav.href));
  if (item?.labelKey) return t(item.labelKey);
  if (pathname.startsWith("/faq")) return "FAQ";
  return "NyaGallery";
}
