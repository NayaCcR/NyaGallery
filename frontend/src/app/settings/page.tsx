"use client";

import { useEffect, useState } from "react";
import { Copy, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import type { ApiAddressesResponse } from "@/lib/types";

export default function SettingsPage() {
  const { t } = useI18n();
  const toast = useToast();
  const [addresses, setAddresses] = useState<ApiAddressesResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void NyaApi.apiAddresses().then(setAddresses).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const entries = addresses ? (["metadata", "preview", "thumb", "original", "short_link_create"] as const) : [];
  return <main className="mx-auto max-w-3xl space-y-6 p-6">
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <h1 className="flex items-center gap-2 text-lg font-semibold"><KeyRound className="h-5 w-5" />{t("pages.settings.apiAddresses")}</h1>
      <p className="text-sm text-muted-foreground">{t("pages.settings.apiAddressesHint")}</p>
      {error && <p className="rounded-md border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
      {!addresses && !error && <p className="text-sm text-muted-foreground">{t("pages.settings.loading")}</p>}
      {addresses && <div className="space-y-3">{entries.map((key) => <div key={key} className="flex items-center gap-2"><div className="min-w-0 flex-1"><div className="mb-1 text-xs font-medium text-muted-foreground">{key}</div><code className="block overflow-x-auto rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">{addresses[key]}</code></div><Button variant="ghost" size="icon" title={t("pages.settings.copyAddress")} onClick={() => void navigator.clipboard?.writeText(addresses[key])}><Copy className="h-4 w-4" /></Button></div>)}</div>}
      {addresses && <p className="text-xs text-muted-foreground">{t("pages.settings.scopeHint")}</p>}
    </section>
  </main>;
}
