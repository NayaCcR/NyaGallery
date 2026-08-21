"use client";

import { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowDownAZ, ArrowUpAZ, Clock } from "lucide-react";
import { PostFeed } from "@/components/posts/post-feed";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { usePosts } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { PostSort, SearchOrder } from "@/lib/types";

function normalizeOrder(value: string | null): SearchOrder {
  return value === "asc" ? "asc" : "desc";
}

function normalizeSort(value: string | null): PostSort {
  return value === "added" ? "added" : "posted_at";
}

/** One control cycling newest posted -> oldest posted -> most recently archived. */
const SORT_MODES: Array<{ sort: PostSort; order: SearchOrder; labelKey: string; icon: typeof ArrowDownAZ }> = [
  { sort: "posted_at", order: "desc", labelKey: "pages.posts.orderDesc", icon: ArrowDownAZ },
  { sort: "posted_at", order: "asc", labelKey: "pages.posts.orderAsc", icon: ArrowUpAZ },
  { sort: "added", order: "desc", labelKey: "pages.posts.orderAdded", icon: Clock },
];

function modeIndex(sort: PostSort, order: SearchOrder): number {
  const found = SORT_MODES.findIndex((mode) => mode.sort === sort && mode.order === order);
  return found >= 0 ? found : 0;
}

function normalizeSource(value: string | null): string {
  return (value ?? "").trim().toLowerCase();
}

function PostsContent() {
  const { t } = useI18n();
  const params = useSearchParams();
  const router = useRouter();
  const source = useMemo(() => normalizeSource(params?.get("source") ?? null), [params]);
  const order = useMemo(() => normalizeOrder(params?.get("order") ?? null), [params]);
  const sort = useMemo(() => normalizeSort(params?.get("sort") ?? null), [params]);
  const { data } = usePosts("", order, { sort });
  const sources = data?.pages[0]?.sources ?? [];
  const total = data?.pages[0]?.total ?? 0;

  function update(next: { source?: string; sort?: PostSort; order?: SearchOrder }) {
    const search = new URLSearchParams();
    const nextSource = next.source ?? source;
    if (nextSource) search.set("source", nextSource);
    const nextSort = next.sort ?? sort;
    if (nextSort !== "posted_at") search.set("sort", nextSort);
    search.set("order", next.order ?? order);
    router.push(`/posts?${search.toString()}`);
  }

  const mode = SORT_MODES[modeIndex(sort, order)];
  const nextMode = SORT_MODES[(modeIndex(sort, order) + 1) % SORT_MODES.length];
  const ModeIcon = mode.icon;

  return (
    <div className="container py-6">
      <header className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("pages.posts.title")}</h1>
          <p className="mt-1 text-xs text-muted-foreground">{t("pages.posts.description")}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="flex max-w-full flex-wrap gap-1 rounded-lg border border-border bg-muted/40 p-1">
            <SourceChip
              label={t("pages.posts.allSources")}
              count={total}
              active={!source}
              onClick={() => update({ source: "" })}
            />
            {sources.map((item) => (
              <SourceChip
                key={item.source}
                label={sourceLabel(item.source, t)}
                count={item.count}
                active={source === item.source}
                onClick={() => update({ source: item.source })}
              />
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => update({ sort: nextMode.sort, order: nextMode.order })}
            title={t("pages.posts.orderNext", { next: t(nextMode.labelKey) })}
            className="gap-1.5"
          >
            <ModeIcon className="h-3.5 w-3.5" />
            {t(mode.labelKey)}
          </Button>
        </div>
      </header>

      <PostFeed source={source} sort={sort} order={order} />
    </div>
  );
}

function SourceChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:bg-background/70 hover:text-foreground"
      )}
    >
      <span>{label}</span>
      <span className="text-[10px] opacity-60">{count}</span>
    </button>
  );
}

function sourceLabel(source: string, t: (key: string) => string): string {
  const label = t(`pages.posts.sources.${source}`);
  return label === `pages.posts.sources.${source}` ? source : label;
}

function PostsFallback() {
  const { t } = useI18n();
  return <div className="container py-6 text-sm text-muted-foreground">{t("common.loading")}</div>;
}

export default function PostsPage() {
  return (
    <Suspense fallback={<PostsFallback />}>
      <PostsContent />
    </Suspense>
  );
}
