"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ImageOff } from "lucide-react";
import { MasonryGrid } from "@/components/gallery/masonry-grid";
import { AssetCardSkeleton } from "@/components/gallery/asset-card";
import { useI18n } from "@/components/providers/locale-provider";
import { useAuth } from "@/components/providers/auth-provider";
import { useContentPreferences } from "@/components/providers/content-preferences-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useIntersection, useTimeline } from "@/lib/hooks";
import { exclusiveUtcNextDay, groupTimelineAssets, isValidTimelineDate, type TimelineGranularity } from "@/lib/timeline";

const FIELDS = ["uploaded_at", "published_at", "captured_at", "scraped_at", "upload_timestamp"] as const;

function TimelineContent() {
  const { t } = useI18n();
  const { ready: authReady } = useAuth();
  const { ready: contentReady, applyContentFilters } = useContentPreferences();
  const [field, setField] = useState<string>("uploaded_at");
  const [granularity, setGranularity] = useState<TimelineGranularity>("day");
  const [selectedDate, setSelectedDate] = useState("");
  const [dateError, setDateError] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);
  const visible = useIntersection(sentinel, { rootMargin: "1200px 0px" });
  const validDate = !selectedDate || isValidTimelineDate(selectedDate);
  const before = selectedDate ? exclusiveUtcNextDay(selectedDate) : null;
  const contentQuery = useMemo(() => applyContentFilters(""), [applyContentFilters]);
  const query = useTimeline(field, before, { enabled: authReady && contentReady && validDate && !dateError, q: contentQuery });
  const items = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  const groups = useMemo(() => groupTimelineAssets(items, granularity), [items, granularity]);

  useEffect(() => {
    if (visible && !query.error && query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
  }, [visible, query.error, query.hasNextPage, query.isFetchingNextPage, query.fetchNextPage]);

  return (
    <div className="container space-y-6 py-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2"><CalendarDays className="h-5 w-5" /><h1 className="text-2xl font-semibold">{t("pages.timeline.title")}</h1></div>
        <div className="flex flex-wrap gap-2">
          <select aria-label={t("pages.timeline.field")} value={field} onChange={(event) => setField(event.target.value)} className="h-9 rounded-md border border-border bg-background px-3 text-sm">
            {FIELDS.map((value) => <option key={value} value={value}>{t(`pages.files.sort.${value}`)}</option>)}
          </select>
          <select aria-label={t("pages.timeline.granularity")} value={granularity} onChange={(event) => setGranularity(event.target.value as "day" | "month" | "year")} className="h-9 rounded-md border border-border bg-background px-3 text-sm">
            <option value="day">{t("pages.timeline.day")}</option><option value="month">{t("pages.timeline.month")}</option><option value="year">{t("pages.timeline.year")}</option>
          </select>
          <label className="flex items-center gap-2 text-sm"><span>{t("pages.timeline.beforeDate")}</span><input type="date" value={selectedDate} onChange={(event) => { const value = event.target.value; setSelectedDate(value); setDateError(Boolean(value) && !isValidTimelineDate(value)); }} className="h-9 rounded-md border border-border bg-background px-2" /></label>
        </div>
      </header>
      {dateError && <p className="text-sm text-destructive">{t("pages.timeline.invalidDate")}</p>}
      {query.isPending ? <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>{Array.from({ length: 8 }).map((_, index) => <AssetCardSkeleton key={index} />)}</div> : query.error ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-10 text-center"><ImageOff className="h-8 w-8 text-destructive" /><p className="text-sm text-destructive">{query.error.message}</p><Button variant="outline" size="sm" onClick={() => query.refetch()}>{t("common.retry")}</Button></div>
      ) : groups.length === 0 ? <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border p-12 text-center"><ImageOff className="h-8 w-8 text-muted-foreground" /><p className="text-sm text-muted-foreground">{t("pages.timeline.empty")}</p></div> : (
        <div className="space-y-10">{groups.map(([date, assets]) => <section key={date} className="space-y-3"><h2 className="text-lg font-semibold tracking-tight">{date === "unknown" ? t("pages.timeline.unknown") : formatDate(date)}</h2><MasonryGrid assets={assets} collapseWorks /></section>)}</div>
      )}
      <div ref={sentinel} className="flex h-16 items-center justify-center">{query.isFetchingNextPage ? <Spinner /> : !query.hasNextPage && items.length > 0 ? <span className="text-xs text-muted-foreground">{t("gallery.end")}</span> : null}</div>
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(`${value}${value.length === 4 ? "-01-01" : value.length === 7 ? "-01" : ""}T00:00:00Z`);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { timeZone: "UTC", dateStyle: "full" }).format(date);
}

function TimelineFallback() { return <div className="container py-6 text-sm text-muted-foreground">Loading...</div>; }
export default function TimelinePage() { return <Suspense fallback={<TimelineFallback />}><TimelineContent /></Suspense>; }
