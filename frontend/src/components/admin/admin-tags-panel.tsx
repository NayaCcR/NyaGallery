"use client";

import type { Dispatch, SetStateAction } from "react";
import { FileJson, RefreshCw, Save, Search, Tags } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/components/providers/locale-provider";
import type { TagSummaryItem } from "@/lib/types";

type AdminTagsPanelProps = {
  busy: string | null;
  filteredTags: TagSummaryItem[];
  tagFilter: string;
  onTagFilterChange: (value: string) => void;
  aliasDrafts: Record<string, string>;
  onAliasDraftsChange: Dispatch<SetStateAction<Record<string, string>>>;
  implicationDrafts: Record<string, string>;
  onImplicationDraftsChange: Dispatch<SetStateAction<Record<string, string>>>;
  summaryPath: string | null;
  onRefreshTags: () => unknown;
  onExportTagSummary: () => unknown;
  onSaveAliases: (tagName: string) => unknown;
  onSaveImplications: (tagName: string) => unknown;
};

export function AdminTagsPanel({
  busy,
  filteredTags,
  tagFilter,
  onTagFilterChange,
  aliasDrafts,
  onAliasDraftsChange,
  implicationDrafts,
  onImplicationDraftsChange,
  summaryPath,
  onRefreshTags,
  onExportTagSummary,
  onSaveAliases,
  onSaveImplications,
}: AdminTagsPanelProps) {
  const { t } = useI18n();

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <Tags className="h-4 w-4" /> {t("admin.tags.title")}
        </h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={busy === "tag-refresh"} onClick={onRefreshTags}>
            <RefreshCw className="h-4 w-4" /> {t("common.refresh")}
          </Button>
          <Button variant="outline" size="sm" disabled={busy === "tag-export"} onClick={onExportTagSummary}>
            <FileJson className="h-4 w-4" /> {t("admin.tags.exportSummary")}
          </Button>
        </div>
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input value={tagFilter} onChange={(e) => onTagFilterChange(e.target.value)} placeholder={t("admin.tags.searchPlaceholder")} className="pl-8" />
      </div>
      {summaryPath && <div className="rounded-md border border-border bg-muted p-2 text-xs text-muted-foreground">{summaryPath}</div>}
      <div className="max-h-[520px] overflow-auto rounded-lg border border-border">
        {filteredTags.map((tag) => (
          <div key={tag.name} className="grid gap-2 border-b border-border p-3 last:border-b-0 sm:grid-cols-[220px_1fr_auto] sm:items-center">
            <div className="min-w-0">
              <div className="truncate font-mono text-xs font-medium" title={tag.name}>{tag.name}</div>
              <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                <span className="rounded border border-border px-1">{tag.category}</span>
                <span className="rounded border border-border px-1">{tag.count}</span>
                <span className="rounded border border-border px-1">{tag.source}</span>
              </div>
            </div>
            <Input
              value={aliasDrafts[tag.name] ?? ""}
              onChange={(e) => onAliasDraftsChange((drafts) => ({ ...drafts, [tag.name]: e.target.value }))}
              placeholder="alias1, alias2"
              className="font-mono text-xs"
            />
            <Input
              value={implicationDrafts[tag.name] ?? ""}
              onChange={(e) => onImplicationDraftsChange((drafts) => ({ ...drafts, [tag.name]: e.target.value }))}
              placeholder={t("admin.tags.implicationPlaceholder")}
              className="font-mono text-xs"
            />
            <Button
              size="sm"
              variant="outline"
              disabled={busy === `tag-${tag.name}` || tag.source === "observed"}
              onClick={() => onSaveAliases(tag.name)}
              title={tag.source === "observed" ? t("admin.tags.createFirst") : t("admin.tags.saveAlias")}
            >
              <Save className="h-4 w-4" /> {t("common.save")}
            </Button>
            <Button size="sm" variant="outline" disabled={busy === `tag-relations-${tag.name}` || tag.source === "observed"} onClick={() => onSaveImplications(tag.name)}>
              <Save className="h-4 w-4" /> {t("admin.tags.saveRelations")}
            </Button>
          </div>
        ))}
        {filteredTags.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("pages.search.tagsEmpty")}</div>}
      </div>
    </section>
  );
}
