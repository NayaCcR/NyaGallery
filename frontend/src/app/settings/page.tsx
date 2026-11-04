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
  const [invitations, setInvitations] = useState<Array<{ id: number; group_id: number; group_name: string; created_at: string | null }>>([]);
  const [shortLinks, setShortLinks] = useState<Array<{ id: number; slug: string; asset_key: string; expires_at: string | null; revoked_at: string | null }>>([]);
  const [shortLinkDrafts, setShortLinkDrafts] = useState<Record<number, string>>({});
  const [error, setError] = useState("");

  async function refreshInvitations() {
    try { setInvitations((await NyaApi.myShareGroupInvitations()).items); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  useEffect(() => {
    void NyaApi.apiAddresses().then(setAddresses).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
    void refreshInvitations();
    void NyaApi.myShortLinks().then((response) => { setShortLinks(response.items); setShortLinkDrafts(Object.fromEntries(response.items.map((item) => [item.id, item.slug]))); }).catch(() => undefined);
  }, []);

  async function saveShortLink(id: number) {
    try {
      const updated = await NyaApi.updateShortLink(id, (shortLinkDrafts[id] ?? "").trim());
      setShortLinks((current) => current.map((item) => item.id === id ? updated : item));
      toast.success(t("pages.settings.shortLinkSaved"));
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : String(reason)); }
  }

  async function respondToInvitation(inviteId: number, decision: "accept" | "decline") {
    try {
      await NyaApi.respondShareGroupInvitation(inviteId, decision);
      await refreshInvitations();
      toast.success(t(decision === "accept" ? "pages.settings.inviteAccepted" : "pages.settings.inviteDeclined"));
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : String(reason)); }
  }

  const entries = addresses ? (["metadata", "preview", "thumb", "original", "short_link_create"] as const) : [];
  return <main className="mx-auto max-w-3xl space-y-6 p-6">
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <h2 className="text-base font-semibold">{t("pages.settings.groupInvites")}</h2>
      {invitations.length === 0 ? <p className="text-sm text-muted-foreground">{t("pages.settings.noGroupInvites")}</p> : <div className="divide-y divide-border">{invitations.map((invite) => <div key={invite.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><span className="text-sm">{invite.group_name}</span><div className="flex gap-2"><Button variant="outline" onClick={() => void respondToInvitation(invite.id, "decline")}>{t("pages.settings.declineInvite")}</Button><Button onClick={() => void respondToInvitation(invite.id, "accept")}>{t("pages.settings.acceptInvite")}</Button></div></div>)}</div>}
    </section>
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm"><h2 className="text-base font-semibold">{t("pages.settings.shortLinks")}</h2>{shortLinks.length === 0 ? <p className="text-sm text-muted-foreground">{t("pages.settings.noShortLinks")}</p> : <div className="divide-y divide-border">{shortLinks.map((link) => <div key={link.id} className="grid gap-2 py-3 sm:grid-cols-[1fr_1fr_auto] sm:items-center"><span className="truncate text-xs text-muted-foreground">{link.asset_key}</span><input value={shortLinkDrafts[link.id] ?? ""} onChange={(event) => setShortLinkDrafts((current) => ({ ...current, [link.id]: event.target.value }))} aria-label={t("pages.settings.shortSlug")} className="h-9 rounded-md border border-input bg-background px-3 text-sm" /><Button variant="outline" size="sm" onClick={() => void saveShortLink(link.id)}>{t("pages.settings.saveShortLink")}</Button></div>)}</div>}</section>
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
