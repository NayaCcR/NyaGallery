"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "@/components/providers/theme-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { THEME_PALETTES } from "@/lib/theme-palettes";
import { cn } from "@/lib/utils";

const MODES: Array<{ value: Theme; icon: typeof Sun }> = [
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
  { value: "system", icon: Monitor },
];

/** Header control: light / dark / system mode plus a colour palette picker. */
export function ThemeToggle() {
  const { theme, resolved, palette, setTheme, setPalette } = useTheme();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={rootRef}>
      <Button
        variant="ghost"
        size="icon"
        className="control-glow"
        aria-label={t("theme.toggle")}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={t("theme.toggle")}
        onClick={() => setOpen((value) => !value)}
      >
        {resolved === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
      {open && (
        <div
          role="dialog"
          aria-label={t("theme.toggle")}
          className="absolute right-0 top-full z-50 mt-2 w-72 origin-top-right animate-scale-in space-y-3 rounded-lg border border-border bg-popover p-3 text-popover-foreground shadow-xl"
        >
          <div className="space-y-1.5">
            <div className="text-[11px] font-medium text-muted-foreground">{t("theme.mode")}</div>
            <div className="grid grid-cols-3 gap-1 rounded-md border border-border bg-muted/40 p-0.5">
              {MODES.map(({ value, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={theme === value}
                  onClick={() => setTheme(value)}
                  className={cn(
                    "flex h-8 items-center justify-center gap-1 rounded text-xs focus-ring",
                    theme === value ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" /> {t(`theme.modes.${value}`)}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <div className="text-[11px] font-medium text-muted-foreground">{t("theme.palette")}</div>
            <div className="grid grid-cols-3 gap-1.5">
              {THEME_PALETTES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={palette === item.id}
                  onClick={() => setPalette(item.id)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-left text-[11px] focus-ring",
                    palette === item.id ? "border-primary/60 bg-primary/5" : "border-border hover:bg-muted"
                  )}
                >
                  <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full" style={{ background: item.swatch }}>
                    {palette === item.id && <Check className="h-2.5 w-2.5 text-white" />}
                  </span>
                  <span className="truncate">{t(`theme.palettes.${item.id}`)}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
