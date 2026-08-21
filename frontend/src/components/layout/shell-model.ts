import type { LucideIcon } from "lucide-react";
import type { AdminSection } from "@/lib/admin-sections";
import type { Branding, LayoutStyle } from "@/lib/branding";

export type ShellNavItem = {
  href: string;
  icon: LucideIcon;
  label: string;
  section?: AdminSection;
  active: boolean;
};

export type ShellNavGroup = {
  id: string;
  label: string;
  items: ShellNavItem[];
};

/**
 * Everything the shell variants need, precomputed by AppShell so the layouts
 * stay purely presentational and a new variant needs no extra wiring.
 */
export type ShellModel = {
  branding: Branding;
  groups: ShellNavGroup[];
  /** Flat list for the mobile / inline nav row, admin sections folded in. */
  inlineItems: ShellNavItem[];
  /** Admin sub-navigation, rendered nested under the workspace group. */
  adminItems: ShellNavItem[];
  showAdminSubnav: boolean;
  headerTitle: string;
  repositoryUrl: string;
  icpBeian: string | null;
  layout: LayoutStyle;
  layoutSwitchable: boolean;
  sidebarCollapsed: boolean;
  onChangeLayout: (layout: LayoutStyle) => void;
  onCollapseSidebar: (collapsed: boolean) => void;
  mobileOpen: boolean;
  onToggleMobile: () => void;
  onCloseMobile: () => void;
};
