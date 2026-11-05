"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Eye, Link2, Loader2, Play, Settings2, Wand2, XCircle } from "lucide-react";
import { SyncCard, SyncNotice } from "@/components/admin/admin-sync-shared";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { getAdminSectionHref, type AdminSection } from "@/lib/admin-sections";
import { NyaApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PixivPreviewItem, SyncResolveResponse, SyncTarget } from "@/lib/types";

/** How a resolved target is dispatched; filled in by the admin page from each platform's remembered settings. */
export type SyncCenterDispatch = (target: SyncTarget) => Promise<string>;

type RowState = { status: "pending" | "running" | "done" | "error"; message?: string };

const PLATFORM_SECTION: Record<string, AdminSection> = { pixiv: "pixiv", x: "x", fanbox: "fanbox", misskey: "misskey" };

/**
 * Unified sync entry: paste any mix of Pixiv / X / FANBOX / Misskey links or ids, see how each was
 * classified, optionally preview Pixiv artworks, then sync the selected ones in one go. Credentials and
 * fetch options come from each platform's own section, so nothing has to be chosen twice.
 */
export function AdminSyncCenterPanel({
  dispatch,
  enabledPlatforms,
  onFinished,
  previewOptions,
}: {
  dispatch: SyncCenterDispatch;
  enabledPlatforms: Record<string, boolean>;
  onFinished: () => unknown;
  previewOptions: Parameters<typeof NyaApi.previewPixiv>[1];
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [resolved, setResolved] = useState<SyncResolveResponse | null>(null);
  const [resolving, setResolving] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [running, setRunning] = useState(false);
  const [previews, setPreviews] = useState<Record<string, PixivPreviewItem>>({});
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const items = useMemo(() => resolved?.items ?? [], [resolved]);
  const actionable = useMemo(
    () => items.map((item, index) => ({ item, index })).filter(({ item }) => isActionable(item) && enabledPlatforms[item.platform]),
    [items, enabledPlatforms]
  );
  const pixivArtworks = actionable.filter(({ item }) => item.platform === "pixiv" && item.kind === "artwork");

  async function resolve() {
    setResolving(true);
    setError(null);
    try {
      const result = await NyaApi.resolveSyncTargets(text);
      setResolved(result);
      setRows({});
      setPreviews({});
      setSelected(
        new Set(
          result.items
            .map((item, index) => ({ item, index }))
            .filter(({ item }) => isActionable(item) && enabledPlatforms[item.platform])
            .map(({ index }) => index)
        )
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setResolving(false);
    }
  }

  async function preview() {
    const pids = pixivArtworks.map(({ item }) => item.value).slice(0, 30);
    if (pids.length === 0) return;
    setPreviewing(true);
    setError(null);
    try {
      const result = await NyaApi.previewPixiv(pids, { ...previewOptions, dry_run: true });
      setPreviews(Object.fromEntries(result.items.map((entry) => [entry.pixiv_id, entry])));
      // Unselect works already in the library so a plain "sync" only fetches new ones.
      setSelected((current) => {
        const next = new Set(current);
        for (const { item, index } of pixivArtworks) {
          if (result.items.find((entry) => entry.pixiv_id === item.value)?.already_archived) next.delete(index);
        }
        return next;
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setPreviewing(false);
    }
  }

  async function runSelected() {
    const queue = actionable.filter(({ index }) => selected.has(index));
    if (queue.length === 0) return;
    setRunning(true);
    setRows(Object.fromEntries(queue.map(({ index }) => [index, { status: "pending" } as RowState])));
    for (const { item, index } of queue) {
      setRows((current) => ({ ...current, [index]: { status: "running" } }));
      try {
        const message = await dispatch(item);
        setRows((current) => ({ ...current, [index]: { status: "done", message } }));
      } catch (exc) {
        setRows((current) => ({ ...current, [index]: { status: "error", message: exc instanceof Error ? exc.message : String(exc) } }));
      }
    }
    setRunning(false);
    await Promise.resolve(onFinished());
  }

  const toggle = (index: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  const allSelected = actionable.length > 0 && actionable.every(({ index }) => selected.has(index));
  const doneCount = Object.values(rows).filter((row) => row.status === "done").length;
  const errorCount = Object.values(rows).filter((row) => row.status === "error").length;

  return (
    <div className="space-y-6">
      <SyncCard icon={Link2} title={t("admin.syncCenter.title")} description={t("admin.syncCenter.description")}>
        <textarea
          className="flex min-h-[140px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs leading-5 focus-ring"
          value={text}
          placeholder={"https://www.pixiv.net/artworks/143748487\nhttps://x.com/someone/status/1855000000000000000\nhttps://nekoworks.fanbox.cc/posts/9261015\n@ks_aya@misskey.io"}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) void resolve();
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={!text.trim() || resolving || running} onClick={() => void resolve()}>
            {resolving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />} {t("admin.syncCenter.resolve")}
          </Button>
          <span className="text-[11px] text-muted-foreground">{t("admin.syncCenter.resolveHint")}</span>
        </div>
        {error && <SyncNotice>{error}</SyncNotice>}
      </SyncCard>

      {resolved && (
        <SyncCard
          icon={Eye}
          title={t("admin.syncCenter.resultTitle", { valid: resolved.valid, invalid: resolved.invalid })}
          description={<GroupChips groups={resolved.groups} />}
          actions={
            <>
              {pixivArtworks.length > 0 && (
                <Button variant="outline" size="sm" disabled={previewing || running} onClick={() => void preview()}>
                  {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />} {t("admin.syncCenter.previewPixiv", { count: Math.min(pixivArtworks.length, 30) })}
                </Button>
              )}
              <Button size="sm" disabled={running || selected.size === 0} onClick={() => void runSelected()}>
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} {t("admin.syncCenter.syncSelected", { count: selected.size })}
              </Button>
            </>
          }
        >
          {resolved.truncated && <SyncNotice>{t("admin.syncCenter.truncated")}</SyncNotice>}
          {Object.keys(rows).length > 0 && (
            <div className="text-xs text-muted-foreground">
              {t("admin.syncCenter.progress", { done: doneCount, failed: errorCount, total: Object.keys(rows).length })}
            </div>
          )}
          <div className="overflow-hidden rounded-lg border border-border">
            <label className="flex items-center gap-2 border-b border-border bg-muted/30 px-3 py-2 text-xs">
              <input
                type="checkbox"
                className="h-4 w-4 accent-primary"
                checked={allSelected}
                disabled={running || actionable.length === 0}
                onChange={() => setSelected(allSelected ? new Set() : new Set(actionable.map(({ index }) => index)))}
              />
              {t("admin.syncCenter.selectAll")}
            </label>
            <div className="max-h-[560px] divide-y divide-border overflow-auto">
              {items.map((item, index) => (
                <TargetRow
                  key={`${index}-${item.input}`}
                  item={item}
                  enabled={Boolean(enabledPlatforms[item.platform])}
                  checked={selected.has(index)}
                  disabled={running}
                  state={rows[index]}
                  preview={item.platform === "pixiv" && item.kind === "artwork" ? previews[item.value] : undefined}
                  onToggle={() => toggle(index)}
                />
              ))}
            </div>
          </div>
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Settings2 className="h-3.5 w-3.5" /> {t("admin.syncCenter.settingsHint")}
          </p>
        </SyncCard>
      )}
    </div>
  );
}

function isActionable(item: SyncTarget) {
  return item.kind !== "invalid" && item.kind !== "short_link";
}

function GroupChips({ groups }: { groups: Record<string, number> }) {
  const { t } = useI18n();
  const entries = Object.entries(groups);
  if (entries.length === 0) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-1.5">
      {entries.map(([key, count]) => {
        const [platform, kind] = key.split(":");
        return (
          <span key={key} className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]">
            {t(`admin.syncCenter.platforms.${platform}`)} · {t(`admin.syncCenter.kinds.${kind}`)} {count}
          </span>
        );
      })}
    </span>
  );
}

function TargetRow({
  item,
  enabled,
  checked,
  disabled,
  state,
  preview,
  onToggle,
}: {
  item: SyncTarget;
  enabled: boolean;
  checked: boolean;
  disabled: boolean;
  state?: RowState;
  preview?: PixivPreviewItem;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const actionable = isActionable(item) && enabled;
  const section = PLATFORM_SECTION[item.platform];
  return (
    <div className={cn("flex items-start gap-3 px-3 py-2.5 text-xs", !actionable && "bg-muted/20", state?.status === "error" && "bg-destructive/5")}>
      <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-primary" checked={checked} disabled={!actionable || disabled} onChange={onToggle} />
      {preview?.thumbnail_url && !preview.error && (
        // eslint-disable-next-line @next/next/no-img-element -- proxied pixiv thumbnail, not an optimizable asset
        <img src={preview.thumbnail_url} alt="" loading="lazy" className="h-14 w-14 shrink-0 rounded-md border border-border object-cover" />
      )}
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">{t(`admin.syncCenter.platforms.${item.platform}`)}</span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px]">{t(`admin.syncCenter.kinds.${item.kind}`)}</span>
          {item.value && (
            <span className="font-mono">
              {item.value}
              {item.host ? `@${item.host}` : ""}
            </span>
          )}
          {preview?.already_archived && <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">{t("admin.syncCenter.archived")}</span>}
          {preview?.age_rating && preview.age_rating !== "safe" && <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-[11px] text-destructive">{preview.age_rating.toUpperCase()}</span>}
          {preview?.is_ai_generated && <span className="rounded bg-muted px-1.5 py-0.5 text-[11px]">AI</span>}
        </div>
        {preview && !preview.error && (
          <div className="truncate text-foreground">
            {preview.title} <span className="text-muted-foreground">· {preview.artist_name} · {t("admin.syncCenter.pages", { count: preview.page_count ?? 0 })}</span>
          </div>
        )}
        <div className="truncate text-muted-foreground" title={item.input}>
          {item.input}
        </div>
        {!isActionable(item) && <div className="text-amber-600 dark:text-amber-400">{t(`admin.syncCenter.errors.${item.error || "unrecognized"}`)}</div>}
        {isActionable(item) && !enabled && (
          <div className="text-amber-600 dark:text-amber-400">{t("admin.syncCenter.platformDisabled")}</div>
        )}
        {preview?.error && <div className="text-destructive">{preview.error}</div>}
        {state?.message && <div className={cn(state.status === "error" ? "text-destructive" : "text-muted-foreground")}>{state.message}</div>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <RowStatus state={state} />
        {section && (
          <Link href={getAdminSectionHref(section)} className="text-[11px] text-muted-foreground hover:text-foreground hover:underline">
            {t("admin.syncCenter.openSection")}
          </Link>
        )}
      </div>
    </div>
  );
}

function RowStatus({ state }: { state?: RowState }) {
  if (!state) return null;
  if (state.status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (state.status === "done") return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (state.status === "error") return <XCircle className="h-4 w-4 text-destructive" />;
  return <AlertTriangle className="h-4 w-4 text-muted-foreground/50" />;
}
