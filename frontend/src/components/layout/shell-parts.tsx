"use client";

import Link from "next/link";
import { Github } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
import type { Branding } from "@/lib/branding";

const IMAGEFLOW_URL = "https://github.com/Yuri-NagaSaki/ImageFlow";
const SZURU_URL = "https://github.com/rr-/szurubooru";

export function NavLink({
  href,
  active,
  icon: Icon,
  label,
  nested = false,
  collapsed = false,
  onClick,
}: {
  href: string;
  active: boolean;
  icon: LucideIcon;
  label: string;
  nested?: boolean;
  collapsed?: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      title={label}
      onClick={onClick}
      className={cn(
        "flex h-10 items-center gap-3 rounded-lg border-l-2 border-transparent px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground",
        nested && "h-9 text-xs",
        collapsed && "justify-center border-l-0 px-0",
        active && "border-primary bg-primary/10 text-primary shadow-sm"
      )}
    >
      <Icon className={cn("shrink-0", collapsed ? "h-5 w-5" : "h-4 w-4")} />
      <span className={collapsed ? "sr-only" : "truncate"}>{label}</span>
    </Link>
  );
}

export function InlineNavLink({
  href,
  active,
  icon: Icon,
  label,
  filled = true,
}: {
  href: string;
  active: boolean;
  icon: LucideIcon;
  label: string;
  filled?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 text-sm transition-colors",
          active
            ? "bg-primary/10 text-primary shadow-sm"
            : filled
              ? "bg-muted/60 text-muted-foreground hover:bg-muted/80 hover:text-foreground"
              : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </Link>
  );
}

export function ShellFooter({
  branding,
  repositoryUrl,
  icpBeian,
  className,
}: {
  branding: Branding;
  repositoryUrl: string;
  icpBeian: string | null;
  className?: string;
}) {
  const { t } = useI18n();

  return (
    <footer
      className={cn("border-t border-border bg-background px-4 py-5 text-xs text-muted-foreground", className)}
    >
      <div className="mx-auto grid w-full max-w-6xl gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-center">
        <div className="flex flex-wrap items-center justify-center gap-2 md:justify-start">
          <span>
            {"🐾 "}
            {t("layout.footer.credit", { app: branding.appName, author: "NayaCcR" })}
          </span>
          <FooterIconLink href={repositoryUrl} label={t("layout.footer.repoLabel")}>
            <Github className="h-4 w-4" />
          </FooterIconLink>
        </div>

        <div className="min-h-5 text-center">
          {icpBeian && (
            <a
              href="http://beian.miit.gov.cn"
              rel="external nofollow"
              target="_blank"
              className="underline-offset-4 transition-colors hover:text-foreground hover:underline"
            >
              {icpBeian}
            </a>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 md:justify-end">
          <FooterCredit href={IMAGEFLOW_URL} prefix={"✨"} note={t("layout.footer.inspiredBy")}>
            ImageFlow
          </FooterCredit>
          <FooterCredit href={SZURU_URL} prefix={"❤️"} note={t("layout.footer.thanksTo")}>
            Szurubooru
          </FooterCredit>
        </div>
      </div>
    </footer>
  );
}

function FooterIconLink({ href, label, children }: { href: string; label: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      className="control-glow grid h-7 w-7 place-items-center rounded-lg border border-border/80 bg-muted/35 text-muted-foreground shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
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
      className="control-glow inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/80 bg-muted/30 px-2.5 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
    >
      <span aria-hidden="true">{prefix}</span>
      <span>{note}</span>
      <span className="font-medium text-foreground">{children}</span>
    </a>
  );
}
