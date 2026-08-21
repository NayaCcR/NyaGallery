"use client";

import { useEffect, useMemo, useRef } from "react";
import { MessageSquareText } from "lucide-react";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { usePosts, useIntersection } from "@/lib/hooks";
import { PostCard, PostCardSkeleton } from "./post-card";
import type { PostSort, SearchOrder } from "@/lib/types";

export function PostFeed({
  source = "",
  sort = "posted_at",
  order = "desc",
  query = "",
  enabled = true,
}: {
  source?: string;
  sort?: PostSort;
  order?: SearchOrder;
  query?: string;
  enabled?: boolean;
}) {
  const { t } = useI18n();
  const sentinelRef = useRef<HTMLDivElement>(null);
  const intersecting = useIntersection(sentinelRef, { rootMargin: "1200px 0px" });

  const {
    data,
    error,
    isPending,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = usePosts(source, order, { q: query, enabled, sort });

  const items = useMemo(() => data?.pages.flatMap((page) => page.items) ?? [], [data]);

  useEffect(() => {
    if (!enabled || isPending || error || isFetchingNextPage || !hasNextPage) return;
    if (!intersecting) return;
    fetchNextPage();
  }, [enabled, error, fetchNextPage, hasNextPage, intersecting, isFetchingNextPage, isPending]);

  return (
    <div className="space-y-6">
      {!enabled || isPending ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <PostCardSkeleton key={i} />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-10 text-center">
          <MessageSquareText className="h-8 w-8 text-destructive" />
          <p className="text-sm text-destructive">{error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border p-12 text-center">
          <MessageSquareText className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{t("pages.posts.empty")}</p>
          <p className="text-xs text-muted-foreground/80">{t("pages.posts.emptyDescription")}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((post) => (
            <PostCard key={post.post_key} post={post} />
          ))}
        </div>
      )}
      <div ref={sentinelRef} className="flex h-16 items-center justify-center">
        {isFetchingNextPage && <Spinner />}
        {!isPending && !error && items.length > 0 && !hasNextPage && (
          <span className="text-xs text-muted-foreground">{t("gallery.end")}</span>
        )}
      </div>
    </div>
  );
}
