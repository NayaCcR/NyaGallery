import {
  Activity,
  ArrowRightLeft,
  AtSign,
  BadgeDollarSign,
  Database,
  Globe2,
  Hash,
  KeyRound,
  LayoutDashboard,
  Link2,
  Puzzle,
  Settings2,
  Shield,
  Tags,
  UsersRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { AdminSection } from "@/lib/admin-sections";

/** Single source for admin section icons (sidebar navigation and the dashboard cards). */
export const ADMIN_SECTION_ICONS: Record<AdminSection, LucideIcon> = {
  dashboard: LayoutDashboard,
  sync: Link2,
  pixiv: Globe2,
  misskey: AtSign,
  x: Hash,
  fanbox: BadgeDollarSign,
  operations: Activity,
  security: Shield,
  tags: Tags,
  maintenance: Database,
  accounts: KeyRound,
  access: UsersRound,
  migration: ArrowRightLeft,
  plugins: Puzzle,
  developer: Settings2,
};
