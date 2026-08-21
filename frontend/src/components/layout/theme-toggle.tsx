"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolved, toggle } = useTheme();
  const { t } = useI18n();
  return (
    <Button
      variant="ghost"
      size="icon"
      className="control-glow"
      aria-label={t("theme.toggle")}
      onClick={toggle}
      title={resolved === "dark" ? t("theme.toLight") : t("theme.toDark")}
    >
      {resolved === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
