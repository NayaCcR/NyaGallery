"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowDownAZ,
  ArrowUpAZ,
  CalendarDays,
  Clock,
  FileText,
  Hash,
  Images,
  PenLine,
  Type,
} from "lucide-react";
import { ContentFilterToggles } from "@/components/content/content-filter-toggles";
import { SensitiveHiddenNotice } from "@/components/content/sensitive-hidden-notice";
import { InfiniteGallery } from "@/components/gallery/infinite-gallery";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { SwitchLabel } from "@/components/ui/switch-label";
import { useBrowseGalleryQueries } from "@/hooks/gallery/use-browse-gallery-queries";
import { cn } from "@/lib/utils";
import type { SearchOrder, SearchSort } from "@/lib/types";

const SORT_OPTIONS: Array<{
  value: SearchSort;
  labelKey: string;
  icon: typeof CalendarDays;
}> = [
  { value: "artwork_date", labelKey: "pages.files.sort.artwork_date", icon: CalendarDays },
  { value: "uploaded_at", labelKey: "pages.files.sort.uploaded_at", icon: Clock },
  { value: "published_at", labelKey: "pages.files.sort.published_at", icon: CalendarDays },
  { value: "captured_at", labelKey: "pages.files.sort.captured_at", icon: CalendarDays },
  { value: "scraped_at", labelKey: "pages.files.sort.scraped_at", icon: Clock },
  { value: "upload_timestamp", labelKey: "pages.files.sort.upload_timestamp", icon: Clock },
  { value: "pixiv_upload_date", labelKey: "pages.files.sort.pixiv_upload_date", icon: Images },
  { value: "original_filename", labelKey: "pages.files.sort.original_filename", icon: FileText },
  { value: "title", labelKey: "pages.files.sort.title", icon: Type },
  { value: "artist", labelKey: "pages.files.sort.artist", icon: PenLine },
  { value: "source_id", labelKey: "pages.files.sort.source_id", icon: Hash },
];

const SORT_VALUES = new Set<SearchSort>(SORT_OPTIONS.map((item) => item.value));

function normalizeSort(value: string | null): SearchSort {
  return value && SORT_VALUES.has(value as SearchSort) ? (value as SearchSort) : "artwork_date";
}

function normalizeOrder(value: string | null): SearchOrder {
  return value === "asc" ? "asc" : "desc";
}

function FilesContent() {
  const { t } = useI18n();
  const params = useSearchParams();
  const router = useRouter();
  const sort = useMemo(() => normalizeSort(params?.get("sort") ?? null), [params]);
  const order = useMemo(() => normalizeOrder(params?.get("order") ?? null), [params]);
  const [collapseWorks, setCollapseWorks] = useState(true);
  const {
    queries: effectiveQueries,
    primaryQuery: effectiveQuery,
    ready: contentReady,
  } = useBrowseGalleryQueries("");

  function update(next: { sort?: SearchSort; order?: SearchOrder }) {
    const search = new URLSearchParams();
    search.set("sort", next.sort ?? sort);
    search.set("order", next.order ?? order);
    router.push(`/files?${search.toString()}`);
  }

  const DirectionIcon = order === "desc" ? ArrowDownAZ : ArrowUpAZ;

  return (
    <div className="container py-6">
      <header className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("pages.files.title")}</h1>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <ContentFilterToggles className="mr-1" />
          <SwitchLabel label={t("pages.files.collapseWorks")} checked={collapseWorks} onChange={setCollapseWorks} />
          <div className="flex max-w-full flex-wrap gap-1 rounded-lg border border-border bg-muted/40 p-1">
            {SORT_OPTIONS.map((option) => {
              const Icon = option.icon;
              const active = sort === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => update({ sort: option.value })}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-background/70 hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{t(option.labelKey)}</span>
                </button>
              );
            })}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => update({ order: order === "desc" ? "asc" : "desc" })}
            className="gap-1.5"
          >
            <DirectionIcon className="h-3.5 w-3.5" />
            {order === "desc" ? t("pages.files.orderDesc") : t("pages.files.orderAsc")}
          </Button>
        </div>
      </header>

      <SensitiveHiddenNotice className="mb-4" />

      <InfiniteGallery
        query={effectiveQuery}
        queries={effectiveQueries}
        enabled={contentReady}
        sort={sort}
        order={order}
        collapseWorks={collapseWorks}
      />
    </div>
  );
}

function FilesFallback() {
  const { t } = useI18n();
  return <div className="container py-6 text-sm text-muted-foreground">{t("common.loading")}</div>;
}

export default function FilesPage() {
  return (
    <Suspense fallback={<FilesFallback />}>
      <FilesContent />
    </Suspense>
  );
}
