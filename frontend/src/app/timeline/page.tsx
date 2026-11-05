"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Bookmark, CalendarDays, ImageOff, Trash2, X } from "lucide-react";
import { MasonryGrid } from "@/components/gallery/masonry-grid";
import { AssetCardSkeleton } from "@/components/gallery/asset-card";
import { useI18n } from "@/components/providers/locale-provider";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { useContentPreferences } from "@/components/providers/content-preferences-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { NyaApi } from "@/lib/api";
import { useIntersection, useTimeline } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { TimelineView } from "@/lib/types";
import { exclusiveUtcNextDay, groupTimelineAssets, isValidTimelineDate, type TimelineGranularity } from "@/lib/timeline";

const FIELDS = ["uploaded_at", "published_at", "captured_at", "scraped_at", "upload_timestamp"] as const;
const LEGACY_VIEWS_KEY = "nyagallery.timeline.views";
const controlClass = "h-9 rounded-md border border-input bg-background px-2.5 text-sm focus-ring";

function TimelineContent() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const { ready: authReady, token, me } = useAuth();
  const toast = useToast();
  const signedIn = Boolean(token && me && me.user_id != null);
  const { ready: contentReady, applyContentFilters } = useContentPreferences();
  const [field, setField] = useState<string>("uploaded_at");
  const [granularity, setGranularity] = useState<TimelineGranularity>("day");
  const [selectedDate, setSelectedDate] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [artistFilter, setArtistFilter] = useState("");
  const [ratingFilter, setRatingFilter] = useState("");
  const [savedViews, setSavedViews] = useState<TimelineView[]>([]);
  const [activeView, setActiveView] = useState("");
  const [viewName, setViewName] = useState("");
  const [dateError, setDateError] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);
  const visible = useIntersection(sentinel, { rootMargin: "1200px 0px" });
  const validDate = !selectedDate || isValidTimelineDate(selectedDate);
  const before = selectedDate ? exclusiveUtcNextDay(selectedDate) : null;
  // Saved views live on the server per user; views saved by older builds in localStorage are migrated once.
  useEffect(() => {
    if (!authReady || !signedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const legacy = readLegacyViews();
        for (const view of legacy) await NyaApi.saveTimelineView(view);
        if (legacy.length) window.localStorage.removeItem(LEGACY_VIEWS_KEY);
        const result = await NyaApi.timelineViews();
        if (!cancelled) setSavedViews(result.items);
      } catch {
        /* views are optional; the timeline still works without them */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authReady, signedIn]);
  useEffect(() => {
    setTagFilter(searchParams.get("tag") ?? "");
    setSourceFilter(searchParams.get("source") ?? "");
    setArtistFilter(searchParams.get("artist") ?? "");
    setRatingFilter(searchParams.get("rating") ?? "");
  }, [searchParams]);
  const contentQuery = useMemo(() => applyContentFilters([tagFilter && `tag:${tagFilter}`, sourceFilter && `source:${sourceFilter}`, artistFilter && `artist:${artistFilter}`, ratingFilter && `rating:${ratingFilter}`].filter(Boolean).join(" ")), [applyContentFilters, artistFilter, ratingFilter, sourceFilter, tagFilter]);
  const query = useTimeline(field, before, { enabled: authReady && contentReady && validDate && !dateError, q: contentQuery });
  const filtersActive = Boolean(tagFilter || sourceFilter || artistFilter || ratingFilter || selectedDate);
  const saveView = async () => {
    const name = viewName.trim();
    if (!name) return;
    const view: TimelineView = {
      name,
      tag: tagFilter.trim(),
      source: sourceFilter.trim(),
      artist: artistFilter.trim(),
      rating: (ratingFilter as TimelineView["rating"]) || "",
      field,
      granularity,
      before: selectedDate,
    };
    try {
      const saved = await NyaApi.saveTimelineView(view);
      setSavedViews((current) => [...current.filter((item) => item.name !== saved.name), saved].sort((a, b) => a.name.localeCompare(b.name)));
      setActiveView(saved.name);
      setViewName("");
      toast.success(t("pages.timeline.viewSaved", { name: saved.name }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };
  const loadView = (view: TimelineView) => {
    setTagFilter(view.tag); setSourceFilter(view.source); setArtistFilter(view.artist); setRatingFilter(view.rating);
    setField(view.field || "uploaded_at"); setGranularity(view.granularity || "day"); setSelectedDate(view.before);
    setDateError(Boolean(view.before) && !isValidTimelineDate(view.before));
    setActiveView(view.name);
  };
  const deleteView = async (name: string) => {
    try {
      await NyaApi.deleteTimelineView(name);
      setSavedViews((current) => current.filter((item) => item.name !== name));
      if (activeView === name) setActiveView("");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };
  const clearFilters = () => {
    setTagFilter(""); setSourceFilter(""); setArtistFilter(""); setRatingFilter(""); setSelectedDate(""); setDateError(false); setActiveView("");
  };
  const items = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  const groups = useMemo(() => groupTimelineAssets(items, granularity), [items, granularity]);

  const { error: queryError, hasNextPage, isFetchingNextPage, fetchNextPage } = query;
  useEffect(() => {
    if (visible && !queryError && hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [visible, queryError, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div className="container space-y-6 py-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2"><CalendarDays className="h-5 w-5" /><h1 className="text-2xl font-semibold">{t("pages.timeline.title")}</h1></div>
          <div className="flex flex-wrap items-center gap-2">
            <select aria-label={t("pages.timeline.field")} value={field} onChange={(event) => setField(event.target.value)} className={controlClass}>
              {FIELDS.map((value) => <option key={value} value={value}>{t(`pages.files.sort.${value}`)}</option>)}
            </select>
            <div role="radiogroup" aria-label={t("pages.timeline.granularity")} className="flex rounded-md border border-input bg-muted/40 p-0.5">
              {(["day", "month", "year"] as TimelineGranularity[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={granularity === value}
                  onClick={() => setGranularity(value)}
                  className={cn("h-8 rounded px-3 text-xs font-medium focus-ring", granularity === value ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}
                >
                  {t(`pages.timeline.${value}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/25 p-2.5">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            {t("pages.timeline.beforeDate")}
            <input type="date" value={selectedDate} onChange={(event) => { const value = event.target.value; setSelectedDate(value); setDateError(Boolean(value) && !isValidTimelineDate(value)); setActiveView(""); }} className={controlClass} />
          </label>
          <input aria-label={t("pages.timeline.tagFilter")} value={tagFilter} onChange={(event) => { setTagFilter(event.target.value); setActiveView(""); }} placeholder={t("pages.timeline.tagFilter")} className={cn(controlClass, "w-32")} />
          <input aria-label={t("pages.timeline.sourceFilter")} value={sourceFilter} onChange={(event) => { setSourceFilter(event.target.value); setActiveView(""); }} placeholder={t("pages.timeline.sourceFilter")} className={cn(controlClass, "w-28")} />
          <input aria-label={t("pages.timeline.artistFilter")} value={artistFilter} onChange={(event) => { setArtistFilter(event.target.value); setActiveView(""); }} placeholder={t("pages.timeline.artistFilter")} className={cn(controlClass, "w-32")} />
          <select aria-label={t("pages.timeline.ratingFilter")} value={ratingFilter} onChange={(event) => { setRatingFilter(event.target.value); setActiveView(""); }} className={controlClass}><option value="">{t("pages.timeline.ratingAll")}</option><option value="safe">safe</option><option value="r18">R18</option><option value="r18g">R18G</option></select>
          {filtersActive && (
            <Button size="sm" variant="ghost" className="h-9" onClick={clearFilters}><X className="h-4 w-4" /> {t("pages.timeline.clearFilters")}</Button>
          )}
          {signedIn && (
            <div className="ml-auto flex items-center gap-2">
              <input aria-label={t("pages.timeline.viewName")} value={viewName} onChange={(event) => setViewName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void saveView(); }} placeholder={t("pages.timeline.viewName")} maxLength={60} className={cn(controlClass, "w-32")} />
              <Button size="sm" variant="outline" className="h-9" onClick={() => void saveView()} disabled={!viewName.trim()}><Bookmark className="h-4 w-4" /> {t("pages.timeline.saveView")}</Button>
            </div>
          )}
        </div>
        {savedViews.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">{t("pages.timeline.savedViews")}</span>
            {savedViews.map((view) => (
              <span key={view.name} className={cn("inline-flex h-7 items-center rounded-full border text-xs", activeView === view.name ? "border-primary/50 bg-primary/10" : "border-border bg-background")}>
                <button type="button" onClick={() => loadView(view)} className="h-full rounded-l-full pl-3 pr-1.5 hover:text-primary focus-ring">{view.name}</button>
                <button type="button" onClick={() => void deleteView(view.name)} aria-label={t("pages.timeline.deleteView", { name: view.name })} title={t("pages.timeline.deleteView", { name: view.name })} className="grid h-full w-6 place-items-center rounded-r-full text-muted-foreground hover:text-destructive focus-ring"><Trash2 className="h-3 w-3" /></button>
              </span>
            ))}
          </div>
        )}
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

function readLegacyViews(): TimelineView[] {
  try {
    const raw = window.localStorage.getItem(LEGACY_VIEWS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Record<string, string>;
    return Object.entries(parsed).flatMap(([name, value]) => {
      try {
        const view = JSON.parse(value) as Record<string, string>;
        const rating = ["safe", "r18", "r18g"].includes(view.ratingFilter) ? (view.ratingFilter as TimelineView["rating"]) : "";
        const granularity = ["day", "month", "year"].includes(view.granularity) ? (view.granularity as TimelineView["granularity"]) : "day";
        return [{ name: name.slice(0, 60), tag: view.tagFilter ?? "", source: view.sourceFilter ?? "", artist: view.artistFilter ?? "", rating, field: FIELDS.includes(view.field as (typeof FIELDS)[number]) ? view.field : "uploaded_at", granularity, before: /^\d{4}-\d{2}-\d{2}$/.test(view.selectedDate ?? "") ? view.selectedDate : "" }];
      } catch {
        return [];
      }
    });
  } catch {
    return [];
  }
}

function formatDate(value: string): string {
  const date = new Date(`${value}${value.length === 4 ? "-01-01" : value.length === 7 ? "-01" : ""}T00:00:00Z`);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { timeZone: "UTC", dateStyle: "full" }).format(date);
}

function TimelineFallback() { return <div className="container py-6 text-sm text-muted-foreground">Loading...</div>; }
export default function TimelinePage() { return <Suspense fallback={<TimelineFallback />}><TimelineContent /></Suspense>; }
