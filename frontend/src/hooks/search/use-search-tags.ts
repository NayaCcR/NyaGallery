"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useContentPreferences } from "@/components/providers/content-preferences-provider";
import { useTagSummary } from "@/lib/hooks";
import { isHiddenTag, isTechnicalTag, tagCategory } from "@/lib/utils";
import type { TagSummaryItem } from "@/lib/types";

const SELECTOR_CATEGORIES = ["rating", "meta"];
const ANIMATED_TAG = "meta:animated";
const EXCLUDE_ANIMATED_TAG = `-${ANIMATED_TAG}`;
const SENSITIVE_RATING_TAGS = new Set(["rating:r18", "rating:r18g"]);

export function useSearchTags() {
  const router = useRouter();
  const [selected, setSelected] = useState<string[]>([]);
  const [openSelectors, setOpenSelectors] = useState<Record<string, boolean>>({});
  const [showTechnical, setShowTechnical] = useState(false);
  const [excludeAnimated, setExcludeAnimated] = useState(false);
  const { data, isFetching, error } = useTagSummary();
  const { applyContentFilters, canViewSensitiveContent } = useContentPreferences();

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const { selectorGroups, catalogGroups, technicalGroups, technicalCount } = useMemo(() => {
    const items = data?.items ?? [];
    const selectors: Map<string, TagSummaryItem[]> = new Map();
    const catalog: Map<string, TagSummaryItem[]> = new Map();
    const technical: Map<string, TagSummaryItem[]> = new Map();
    let techCount = 0;

    for (const tag of items) {
      if (isHiddenTag(tag.name)) continue;
      if (!canViewSensitiveContent && SENSITIVE_RATING_TAGS.has(tag.name)) continue;
      const category = tag.category || tagCategory(tag.name);
      const target = isTechnicalTag(tag.name)
        ? technical
        : SELECTOR_CATEGORIES.includes(category)
          ? selectors
          : catalog;
      const list = target.get(category) ?? [];
      list.push(tag);
      target.set(category, list);
      if (target === technical) techCount++;
    }

    for (const [, list] of selectors) list.sort((a, b) => b.count - a.count);
    for (const [, list] of catalog) list.sort((a, b) => b.count - a.count);
    for (const [, list] of technical) list.sort((a, b) => b.count - a.count);

    return {
      selectorGroups: Array.from(selectors.entries()).sort(([a], [b]) => a.localeCompare(b)),
      catalogGroups: Array.from(catalog.entries()).sort(([a], [b]) => a.localeCompare(b)),
      technicalGroups: Array.from(technical.entries()).sort(([a], [b]) => a.localeCompare(b)),
      technicalCount: techCount,
    };
  }, [canViewSensitiveContent, data]);

  const toggle = useCallback((name: string) => {
    setSelected((prev) => {
      if (prev.includes(name)) return prev.filter((tag) => tag !== name);
      return [...prev, name];
    });
  }, []);

  const selectedQueryParts = useCallback(() => {
    const parts = selected.filter(
      (tag) => tag !== EXCLUDE_ANIMATED_TAG && (!excludeAnimated || tag !== ANIMATED_TAG)
    );
    if (excludeAnimated) parts.push(EXCLUDE_ANIMATED_TAG);
    return Array.from(new Set(parts));
  }, [excludeAnimated, selected]);

  const effectiveQueryParts = useMemo(() => {
    const query = applyContentFilters(selectedQueryParts());
    return query ? query.split(/\s+/).filter(Boolean) : [];
  }, [applyContentFilters, selectedQueryParts]);

  const submit = useCallback((overrideParts?: string[]) => {
    const parts = overrideParts ?? selectedQueryParts();
    if (parts.length === 0) {
      router.push("/");
      return;
    }
    const qs = new URLSearchParams({ q: parts.join(" ") }).toString();
    router.push(`/?${qs}`);
  }, [router, selectedQueryParts]);

  return {
    selected,
    setSelected,
    selectedSet,
    selectorGroups,
    catalogGroups,
    technicalGroups,
    technicalCount,
    openSelectors,
    setOpenSelectors,
    showTechnical,
    setShowTechnical,
    excludeAnimated,
    setExcludeAnimated,
    toggle,
    effectiveQueryParts,
    submit,
    isFetching,
    error,
  };
}
