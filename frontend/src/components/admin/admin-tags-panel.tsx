"use client";

import type { Dispatch, SetStateAction } from "react";
import { FileJson, RefreshCw, Save, Search, Tags } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
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
        {filteredTags.map((tag) => {
          const observed = tag.source === "observed";
          return (
            <div key={tag.name} className="grid gap-2 border-b border-border p-3 last:border-b-0 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
              <div className="min-w-0">
                <div className="truncate font-mono text-xs font-medium" title={tag.name}>{tag.name}</div>
                <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                  <span className="rounded border border-border px-1">{tag.category}</span>
                  <span className="rounded border border-border px-1 tabular-nums">{tag.count}</span>
                  <span className={cn("rounded border px-1", observed ? "border-amber-500/40 text-amber-600 dark:text-amber-400" : "border-border")}>{tag.source}</span>
                </div>
              </div>
              <TagField
                label={t("admin.tags.aliases")}
                value={aliasDrafts[tag.name] ?? ""}
                placeholder="alias1, alias2"
                disabled={observed}
                busy={busy === `tag-${tag.name}`}
                title={observed ? t("admin.tags.createFirst") : t("admin.tags.saveAlias")}
                onChange={(value) => onAliasDraftsChange((drafts) => ({ ...drafts, [tag.name]: value }))}
                onSave={() => onSaveAliases(tag.name)}
              />
              <TagField
                label={t("admin.tags.implications")}
                value={implicationDrafts[tag.name] ?? ""}
                placeholder={t("admin.tags.implicationPlaceholder")}
                disabled={observed}
                busy={busy === `tag-relations-${tag.name}`}
                title={observed ? t("admin.tags.createFirst") : t("admin.tags.saveRelations")}
                onChange={(value) => onImplicationDraftsChange((drafts) => ({ ...drafts, [tag.name]: value }))}
                onSave={() => onSaveImplications(tag.name)}
              />
            </div>
          );
        })}        {filteredTags.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("pages.search.tagsEmpty")}</div>}
      </div>
    </section>
  );
}

function TagField({
  label,
  value,
  placeholder,
  disabled,
  busy,
  title,
  onChange,
  onSave,
}: {
  label: string;
  value: string;
  placeholder: string;
  disabled: boolean;
  busy: boolean;
  title: string;
  onChange: (value: string) => void;
  onSave: () => unknown;
}) {
  const { t } = useI18n();
  return (
    <div className="min-w-0 space-y-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="flex gap-1.5">
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !disabled && !busy) void onSave();
          }}
          placeholder={placeholder}
          disabled={disabled}
          className="h-8 font-mono text-xs"
        />
        <Button size="sm" variant="outline" className="h-8 shrink-0 px-2" disabled={disabled || busy} onClick={() => void onSave()} title={title} aria-label={title}>
          <Save className="h-3.5 w-3.5" />
          <span className="sr-only">{t("common.save")}</span>
        </Button>
      </div>
    </div>
  );
}
