"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NyaApi } from "@/lib/api";
import type { EntitySummary } from "@/lib/types";

const EMPTY = { type: "character", entity_id: "", name: "", metadata: "{}", asset_keys: "" };

export default function EntitiesPage() {
  const { t } = useI18n();
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    try { setEntities((await NyaApi.entities()).items); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }
  useEffect(() => { void refresh(); }, []);

  function beginEdit(entity: EntitySummary) {
    setEditingId(entity.id);
    setDraft({ type: entity.type, entity_id: entity.entity_id, name: entity.name, metadata: JSON.stringify(entity.metadata ?? {}, null, 2), asset_keys: entity.asset_keys.join("\n") });
  }
  function reset() { setEditingId(null); setDraft(EMPTY); }

  async function save() {
    setBusy(true); setError("");
    try {
      const metadata = JSON.parse(draft.metadata || "{}");
      const asset_keys = draft.asset_keys.split(/[\s,]+/).map((key) => key.trim()).filter(Boolean);
      const payload = { type: draft.type.trim(), entity_id: draft.entity_id.trim(), name: draft.name.trim(), metadata, asset_keys };
      if (editingId === null) await NyaApi.createEntity(payload); else await NyaApi.updateEntity(editingId, payload);
      reset(); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function remove(entity: EntitySummary) {
    if (!window.confirm(t("pages.entities.confirmDelete", { name: entity.name }))) return;
    setBusy(true);
    try { await NyaApi.deleteEntity(entity.id); if (editingId === entity.id) reset(); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function unlink(entity: EntitySummary, assetKey: string) {
    setBusy(true);
    try { await NyaApi.unlinkEntityAsset(entity.id, assetKey); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  return <main className="container space-y-6 py-6">
    <header><h1 className="text-2xl font-semibold">{t("pages.entities.title")}</h1><p className="mt-1 text-sm text-muted-foreground">{t("pages.entities.description")}</p></header>
    <section className="space-y-4 rounded-lg border border-border bg-card p-5">
      <div className="flex items-center justify-between"><h2 className="font-medium">{editingId === null ? t("pages.entities.create") : t("pages.entities.edit")}</h2>{editingId !== null && <Button variant="ghost" onClick={reset}>{t("common.cancel")}</Button>}</div>
      <div className="grid gap-3 sm:grid-cols-3"><label className="space-y-1"><Label>{t("pages.entities.type")}</Label><Input value={draft.type} onChange={(event) => setDraft({ ...draft, type: event.target.value })} /></label><label className="space-y-1"><Label>{t("pages.entities.entityId")}</Label><Input value={draft.entity_id} onChange={(event) => setDraft({ ...draft, entity_id: event.target.value })} /></label><label className="space-y-1"><Label>{t("pages.entities.name")}</Label><Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label></div>
      <label className="block space-y-1"><Label>{t("pages.entities.assetKeys")}</Label><textarea value={draft.asset_keys} onChange={(event) => setDraft({ ...draft, asset_keys: event.target.value })} placeholder={t("pages.entities.assetKeysPlaceholder")} className="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" /></label>
      <label className="block space-y-1"><Label>{t("pages.entities.metadata")}</Label><textarea value={draft.metadata} onChange={(event) => setDraft({ ...draft, metadata: event.target.value })} className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs" /></label>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button disabled={busy || !draft.type.trim() || !draft.entity_id.trim() || !draft.name.trim()} onClick={() => void save()}>{editingId === null ? t("pages.entities.create") : t("common.save")}</Button>
    </section>
    <section className="space-y-3"><h2 className="font-medium">{t("pages.entities.list")}</h2>{entities.length === 0 ? <p className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">{t("pages.entities.empty")}</p> : entities.map((entity) => <article key={entity.id} className="space-y-3 rounded-lg border border-border bg-card p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs text-muted-foreground">{entity.type} · {entity.entity_id}</div><h3 className="font-medium">{entity.name}</h3></div><div className="flex gap-2"><Link href={`/entities/${entity.id}`}><Button variant="outline" size="sm">{t("pages.entities.timeline")}</Button></Link><Button variant="outline" size="sm" onClick={() => beginEdit(entity)}>{t("common.edit")}</Button><Button variant="ghost" size="sm" onClick={() => void remove(entity)}>{t("common.delete")}</Button></div></div><div className="flex flex-wrap gap-2">{entity.asset_keys.map((key) => <span key={key} className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs"><Link className="underline" href={`/asset/${encodeURIComponent(key)}`}>{key}</Link><button type="button" title={t("pages.entities.unlink")} onClick={() => void unlink(entity, key)} className="text-muted-foreground hover:text-destructive">×</button></span>)}</div></article>)}</section>
  </main>;
}
