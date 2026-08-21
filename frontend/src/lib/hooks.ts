"use client";

import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ApiError, NyaApi } from "./api";
import type { Asset, MeResponse, PostListResponse, PostSort, SearchOrder, SearchResponse, SearchSort, SiteConfigResponse, TagSuggestResponse, TagSummaryResponse } from "./types";

const PAGE_SIZE = 40;
const POSTS_PAGE_SIZE = 20;

export function useSearchAssets(
  query: string | string[],
  sort: SearchSort = "uploaded_at",
  order: SearchOrder = "desc",
  options: { enabled?: boolean } = {}
) {
  const queries = normalizeSearchQueries(query);
  return useInfiniteQuery<SearchPageResponse, Error>({
    queryKey: ["search", queries, sort, order],
    queryFn: async ({ pageParam = 0 }) => {
      const offset = pageParam as number;
      if (queries.length === 1) {
        const page = await NyaApi.search({ q: queries[0], limit: PAGE_SIZE, offset, sort, order });
        return {
          ...page,
          hasMore: page.items.length >= PAGE_SIZE,
        };
      }
      const pages = await Promise.all(
        queries.map((q) => NyaApi.search({ q, limit: PAGE_SIZE, offset, sort, order }))
      );
      return mergeSearchPages(pages, offset, sort, order);
    },
    enabled: options.enabled ?? true,
    initialPageParam: 0,
    getNextPageParam: (last) =>
      last.hasMore ? last.offset + PAGE_SIZE : undefined,
  });
}

type SearchPageResponse = SearchResponse & {
  hasMore: boolean;
};

function normalizeSearchQueries(query: string | string[]): string[] {
  const values = Array.isArray(query) ? query : [query];
  const seen = new Set<string>();
  const queries: string[] = [];
  for (const value of values) {
    const normalized = value.trim().replace(/\s+/g, " ");
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    queries.push(normalized);
  }
  return queries.length > 0 ? queries : [""];
}

function mergeSearchPages(
  pages: SearchResponse[],
  offset: number,
  sort: SearchSort,
  order: SearchOrder
): SearchPageResponse {
  const seen = new Set<string>();
  const items: Asset[] = [];
  for (const page of pages) {
    for (const item of page.items) {
      if (seen.has(item.asset_key)) continue;
      seen.add(item.asset_key);
      items.push(item);
    }
  }

  return {
    items,
    limit: PAGE_SIZE,
    offset,
    sort,
    order,
    hasMore: pages.some((page) => page.items.length >= PAGE_SIZE),
  };
}

export function usePosts(
  source: string = "",
  order: SearchOrder = "desc",
  options: { q?: string; enabled?: boolean; sort?: PostSort } = {}
) {
  const query = options.q ?? "";
  const sort = options.sort ?? "posted_at";
  return useInfiniteQuery<PostListResponse, Error>({
    queryKey: ["posts", source, sort, order, query],
    queryFn: ({ pageParam = 0 }) =>
      NyaApi.posts({ limit: POSTS_PAGE_SIZE, offset: pageParam as number, source, q: query, sort, order }),
    enabled: options.enabled ?? true,
    initialPageParam: 0,
    getNextPageParam: (last) =>
      last.has_more ? last.offset + POSTS_PAGE_SIZE : undefined,
  });
}

export function useAsset(assetKey: string | null | undefined) {
  return useQuery({
    queryKey: ["asset", assetKey],
    queryFn: () => NyaApi.asset(assetKey as string),
    enabled: !!assetKey,
  });
}

export function useAssetSiblings(assetKey: string | null | undefined) {
  return useQuery({
    queryKey: ["asset-siblings", assetKey],
    queryFn: () => NyaApi.assetSiblings(assetKey as string),
    enabled: !!assetKey,
  });
}

export function useTagSuggest(query: string) {
  const debounced = useDebounced(query, 200);
  return useQuery<TagSuggestResponse, Error>({
    queryKey: ["tag-suggest", debounced],
    queryFn: () => NyaApi.tagSuggest(debounced),
    enabled: debounced.trim().length > 0,
    staleTime: 30_000,
  });
}

export function useTagSummary() {
  return useQuery<TagSummaryResponse, Error>({
    queryKey: ["tag-summary"],
    queryFn: () => NyaApi.tagSummary(),
    staleTime: 60_000,
  });
}

export function useMe(sessionVersion: number) {
  return useQuery<MeResponse | null, Error>({
    queryKey: ["me", sessionVersion],
    queryFn: async () => {
      try {
        return await NyaApi.me();
      } catch (err) {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          return null;
        }
        throw err;
      }
    },
    staleTime: 60_000,
  });
}

export function useSiteConfig() {
  return useQuery<SiteConfigResponse, Error>({
    queryKey: ["site-config"],
    queryFn: () => NyaApi.siteConfig(),
    staleTime: 300_000,
  });
}

export function useDebounced<T>(value: T, delay = 200): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useIntersection(
  ref: React.RefObject<Element>,
  options?: IntersectionObserverInit
): boolean {
  const [intersecting, setIntersecting] = useState(false);
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => setIntersecting(entry.isIntersecting),
      optsRef.current
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref]);

  return intersecting;
}
