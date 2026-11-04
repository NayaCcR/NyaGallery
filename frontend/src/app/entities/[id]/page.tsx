"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ImageOff } from "lucide-react";
import { useParams } from "next/navigation";
import { MasonryGrid } from "@/components/gallery/masonry-grid";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useI18n } from "@/components/providers/locale-provider";
import { NyaApi } from "@/lib/api";
import type { EntityTimelineResponse } from "@/lib/types";

export default function EntityTimelinePage() {
  const { t } = useI18n();
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<EntityTimelineResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const id = Number(params.id);
    if (!Number.isInteger(id)) { setError(t("pages.entities.invalidId")); return; }
    setBusy(true);
    void NyaApi.entityTimeline(id, { limit: 48, offset }).then((next) => setData((current) => offset === 0 ? next : ({ ...next, items: [...(current?.items ?? []), ...next.items] }))).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason))).finally(() => setBusy(false));
  }, [offset, params.id, t]);
  return <main className="container space-y-6 py-6"><Link href="/entities" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />{t("pages.entities.back")}</Link>{error ? <p className="text-sm text-destructive">{error}</p> : !data ? <Spinner /> : <><header><div className="text-xs text-muted-foreground">{data.entity.type} · {data.entity.entity_id}</div><h1 className="text-2xl font-semibold">{data.entity.name}</h1></header>{data.items.length === 0 ? <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border p-12 text-center"><ImageOff className="h-8 w-8 text-muted-foreground" /><p className="text-sm text-muted-foreground">{t("pages.entities.emptyTimeline")}</p></div> : <MasonryGrid assets={data.items} collapseWorks />}{data.has_more && <div className="flex justify-center"><Button variant="outline" disabled={busy} onClick={() => setOffset((value) => value + 48)}>{busy ? <Spinner /> : t("common.loadMore")}</Button></div>}</>}</main>;
}
