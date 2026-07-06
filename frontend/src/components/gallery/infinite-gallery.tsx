"use client";

import { useEffect, useMemo, useRef } from "react";
import { ImageOff } from "lucide-react";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useIntersection, useSearchAssets } from "@/lib/hooks";
import { MasonryGrid } from "./masonry-grid";
import { AssetCardSkeleton } from "./asset-card";
import type { Asset, SearchOrder, SearchSort } from "@/lib/types";

const MIN_COLLAPSED_CARDS = 18;
const AUTO_FILL_PAGE_LIMIT = 6;

export function InfiniteGallery({
  query,
  queries,
  sort = "uploaded_at",
  order = "desc",
  enabled = true,
  activeTags,
  onTagClick,
  collapseWorks = true,
}: {
  query: string;
  queries?: string[];
  sort?: SearchSort;
  order?: SearchOrder;
  enabled?: boolean;
  activeTags?: string[];
  onTagClick?: (tag: string) => void;
  collapseWorks?: boolean;
}) {
  const { t } = useI18n();
  const sentinelRef = useRef<HTMLDivElement>(null);
  const intersecting = useIntersection(sentinelRef, { rootMargin: "1200px 0px" });
  const searchQueries = queries && queries.length > 0 ? queries : [query];

  const {
    data,
    error,
    isPending,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useSearchAssets(searchQueries, sort, order, { enabled });

  const items = useMemo(() => data?.pages.flatMap((page) => page.items) ?? [], [data]);
  const visibleItemCount = useMemo(
    () => countVisibleItems(items, collapseWorks),
    [collapseWorks, items]
  );
  const loadedPageCount = data?.pages.length ?? 0;

  useEffect(() => {
    if (!enabled || isPending || error || isFetchingNextPage || !hasNextPage) return;
    const shouldAutoFill =
      collapseWorks &&
      items.length > 0 &&
      visibleItemCount < MIN_COLLAPSED_CARDS &&
      loadedPageCount < AUTO_FILL_PAGE_LIMIT;
    if (!intersecting && !shouldAutoFill) return;
    fetchNextPage();
  }, [
    collapseWorks,
    enabled,
    error,
    fetchNextPage,
    hasNextPage,
    intersecting,
    isFetchingNextPage,
    isPending,
    items.length,
    loadedPageCount,
    visibleItemCount,
  ]);

  return (
    <div className="space-y-6">
      {!enabled || isPending ? (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}
        >
          {Array.from({ length: 12 }).map((_, i) => (
            <AssetCardSkeleton key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-10 text-center">
          <ImageOff className="h-8 w-8 text-destructive" />
          <p className="text-sm text-destructive">{error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border p-12 text-center">
          <ImageOff className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{t("gallery.emptyTitle")}</p>
          <p className="text-xs text-muted-foreground/80">{t("gallery.emptyDescription")}</p>
        </div>
      ) : (
        <MasonryGrid
          assets={items}
          activeTags={activeTags}
          onTagClick={onTagClick}
          collapseWorks={collapseWorks}
        />
      )}
      <div ref={sentinelRef} className="flex h-16 items-center justify-center">
        {isFetchingNextPage && <Spinner />}
        {!hasNextPage && (
          <span className="text-xs text-muted-foreground">{t("gallery.end")}</span>
        )}
      </div>
    </div>
  );
}

function countVisibleItems(assets: Asset[], collapseWorks: boolean): number {
  if (!collapseWorks) return assets.length;
  const groups = new Set<string>();
  for (const asset of assets) {
    groups.add(workGroupKey(asset));
  }
  return groups.size;
}

function workGroupKey(asset: Asset): string {
  return asset.source && asset.source_id
    ? `${asset.source}:${asset.source_id}`
    : asset.asset_key;
}
