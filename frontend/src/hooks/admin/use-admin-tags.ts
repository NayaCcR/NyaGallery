"use client";

import { useCallback, useMemo, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { NyaApi } from "@/lib/api";
import type { TagSummaryItem } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

type UseAdminTagsOptions = {
  run: AdminActionRunner;
};

export function useAdminTags({ run }: UseAdminTagsOptions) {
  const { t } = useI18n();
  const [tags, setTags] = useState<TagSummaryItem[]>([]);
  const [tagFilter, setTagFilter] = useState("");
  const [aliasDrafts, setAliasDrafts] = useState<Record<string, string>>({});
  const [implicationDrafts, setImplicationDrafts] = useState<Record<string, string>>({});
  const [summaryPath, setSummaryPath] = useState<string | null>(null);

  const loadTags = useCallback(async () => {
    const summary = await NyaApi.tagSummary();
    setTags(summary.items);
    setAliasDrafts(Object.fromEntries(summary.items.map((tag) => [tag.name, tag.aliases.join(", ")])));
    setImplicationDrafts(Object.fromEntries(summary.items.map((tag) => [tag.name, tag.implications.join(", ")])));
  }, []);

  const filteredTags = useMemo(() => {
    const needle = tagFilter.trim().toLowerCase();
    if (!needle) return tags;
    return tags.filter((tag) =>
      [tag.name, tag.category, ...tag.aliases].join(" ").toLowerCase().includes(needle)
    );
  }, [tagFilter, tags]);

  const implicationsFromDraft = useCallback(
    (name: string): string[] => Array.from(new Set((implicationDrafts[name] ?? "").split(/[,\n，]/).map((item) => item.trim()).filter(Boolean))),
    [implicationDrafts]
  );

  const aliasesFromDraft = useCallback(
    (name: string): string[] =>
      Array.from(
        new Set(
          (aliasDrafts[name] ?? "")
            .split(/[,\n，]/)
            .map((item) => item.trim())
            .filter(Boolean)
        )
      ),
    [aliasDrafts]
  );

  const saveAliases = useCallback(
    async (tagName: string) => {
      await run(
        `tag-${tagName}`,
        () => NyaApi.updateTagAliases(tagName, aliasesFromDraft(tagName)),
        (tag) => t("admin.tags.aliasSaved", { name: tag.name })
      );
      await loadTags();
    },
    [aliasesFromDraft, loadTags, run, t]
  );

  const saveImplications = useCallback(
    async (tagName: string) => {
      await run(`tag-relations-${tagName}`, () => NyaApi.updateTagRelations(tagName, implicationsFromDraft(tagName)), (tag) => t("admin.tags.relationsSaved", { name: tag.name }));
      await loadTags();
    },
    [implicationsFromDraft, loadTags, run, t]
  );

  const exportTagSummary = useCallback(async () => {
    await run("tag-export", () => NyaApi.exportTagSummary(), (result) => {
      setSummaryPath(result.path);
      return t("admin.tags.exported", { count: result.total });
    });
  }, [run, t]);

  return {
    tags,
    filteredTags,
    tagFilter,
    setTagFilter,
    aliasDrafts,
    setAliasDrafts,
    implicationDrafts,
    setImplicationDrafts,
    summaryPath,
    loadTags,
    saveAliases,
    saveImplications,
    exportTagSummary,
  };
}
