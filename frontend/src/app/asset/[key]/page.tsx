"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Check, Copy, Download, ExternalLink, Tags as TagsIcon, Trash2, AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAsset, useAssetSiblings } from "@/lib/hooks";
import { ApiError, downloadOriginalAsset, fileUrl, NyaApi, readToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { cn, formatDateTime, isAnimatedGifMedia, isHiddenTag, isVideoMedia, sourceTagLabel, sourceTagQuery, sourceTagSecondaryLabel, tagCategory, tagLabel } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import type { Asset } from "@/lib/types";
import { useI18n } from "@/components/providers/locale-provider";

export default function AssetDetailPage() {
  const params = useParams<{ key: string }>();
  const router = useRouter();
  const assetKey = decodeURIComponent(params?.key ?? "");
  const { data: asset, isPending, error, refetch } = useAsset(assetKey);
  const { data: siblingsData } = useAssetSiblings(assetKey);
  const { token, me } = useAuth();
  const toast = useToast();
  const { locale, t } = useI18n();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draftTags, setDraftTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [activeAssetKey, setActiveAssetKey] = useState(assetKey);

  const canDeleteRequest = me?.permissions.includes("delete_request") ?? false;
  const canDelete = me?.permissions.includes("delete") ?? false;
  const pages = useMemo(
    () => siblingsData?.items?.length ? siblingsData.items : asset ? [asset] : [],
    [asset, siblingsData?.items]
  );
  const hasMultiplePages = pages.length > 1;
  const activeAsset = pages.find((page) => page.asset_key === activeAssetKey) ?? asset;
  const activePageIndex = Math.max(0, pages.findIndex((page) => page.asset_key === activeAsset?.asset_key));
  const visibleTags = useMemo(
    () => (asset?.tags ?? []).filter((tag) => !isHiddenTag(tag)),
    [asset?.tags]
  );
  const tagDetails = useMemo(
    () => new Map((asset?.tag_details ?? []).map((tag) => [tag.name, tag])),
    [asset?.tag_details]
  );

  useEffect(() => {
    if (!pages.length) return;
    const hashKey = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    const initialKey = pages.some((page) => page.asset_key === hashKey)
      ? hashKey
      : pages.some((page) => page.asset_key === assetKey)
        ? assetKey
        : pages[0].asset_key;
    setActiveAssetKey(initialKey);
  }, [assetKey, pages]);

  useEffect(() => {
    if (!hasMultiplePages) return;
    const elements = pages
      .map((page) => document.getElementById(page.asset_key))
      .filter((element): element is HTMLElement => element !== null);
    if (!elements.length) return;

    let frame = 0;
    const updateActivePage = () => {
      frame = 0;
      const anchorY = window.innerHeight * 0.35;
      let fallback: { id: string; distance: number } | null = null;
      for (const element of elements) {
        const rect = element.getBoundingClientRect();
        if (rect.top <= anchorY && rect.bottom >= anchorY) {
          setActiveAssetKey(element.id);
          return;
        }
        const distance = rect.top > anchorY ? rect.top - anchorY : anchorY - rect.bottom;
        if (fallback === null || distance < fallback.distance) {
          fallback = { id: element.id, distance };
        }
      }
      if (fallback) setActiveAssetKey(fallback.id);
    };
    const scheduleUpdate = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(updateActivePage);
    };
    const resizeObserver = new ResizeObserver(scheduleUpdate);
    elements.forEach((element) => resizeObserver.observe(element));
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    scheduleUpdate();
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
    };
  }, [hasMultiplePages, pages]);

  if (isPending) {
    return (
      <div className="container grid gap-6 py-6 lg:grid-cols-[1fr_360px]">
        <Skeleton className="aspect-[3/4] w-full" />
        <div className="space-y-3">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    );
  }

  if (error || !asset) {
    return (
      <div className="container flex flex-col items-center gap-4 py-20 text-center">
        <p className="text-sm text-destructive">{error?.message ?? t("common.notFound")}</p>
        <Button onClick={() => router.back()} variant="outline" size="sm">
          {t("common.back")}
        </Button>
      </div>
    );
  }

  function startEdit() {
    setDraftTags((asset!.canonical_tags ?? []).join(" "));
    setEditing(true);
  }

  async function saveTags() {
    if (!asset) return;
    setSaving(true);
    try {
      const next = draftTags.split(/\s+/).filter(Boolean);
      const updated = await NyaApi.updateAssetTags(asset.asset_key, next);
      qc.setQueryData(["asset", asset.asset_key], updated);
      qc.invalidateQueries({ queryKey: ["search"] });
      toast.success(t("common.saved"));
      setEditing(false);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("pages.asset.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function downloadOriginal() {
    if (!activeAsset) return;
    setDownloading(true);
    try {
      await downloadOriginalAsset(activeAsset);
    } catch (e: unknown) {
      toast.error(e instanceof ApiError && e.status === 401
        ? t("pages.asset.downloadLoginRequired")
        : e instanceof Error ? e.message : t("pages.asset.downloadFailed"));
    } finally {
      setDownloading(false);
    }
  }

  async function requestDelete() {
    if (!asset) return;
    if (!confirm(t("pages.asset.deleteConfirm"))) return;
    setDeleting(true);
    try {
      const updated = await NyaApi.deleteAsset(asset.asset_key);
      qc.setQueryData(["asset", asset.asset_key], updated);
      qc.invalidateQueries({ queryKey: ["search"] });
      toast.success(t("pages.asset.deleteQueued"));
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("pages.asset.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  }

  async function purgeAsset() {
    if (!asset) return;
    if (!confirm(t("pages.asset.purgeConfirm"))) return;
    setDeleting(true);
    try {
      await NyaApi.cleanupAsset(asset.asset_key);
      qc.invalidateQueries({ queryKey: ["search"] });
      toast.success(t("pages.asset.purgeDone"));
      router.push("/");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : t("pages.asset.purgeFailed"));
    } finally {
      setDeleting(false);
    }
  }

  const artistUrl = artistHomeUrl(asset);
  const artworkUrl = artworkHomeUrl(asset);

  return (
    <div className="container grid gap-6 py-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.back()}
          className="mb-3"
        >
          <ArrowLeft className="h-4 w-4" /> {t("common.back")}
        </Button>
        <div className="space-y-4">
          {hasMultiplePages && (
            <div className="rounded-lg border border-border bg-muted/25 px-3 py-2 text-xs text-muted-foreground">
              {t("pages.asset.multiPageHint", { count: pages.length })}
            </div>
          )}
          {pages.map((page, index) => (
            <AssetPageImage
              key={page.asset_key}
              asset={page}
              index={index}
              current={page.asset_key === activeAsset?.asset_key}
            />
          ))}
        </div>
      </div>

      <aside className="space-y-5 lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto lg:overscroll-contain lg:pr-2">
        <div>
          <h1 className="text-xl font-semibold leading-tight">
            {asset.title || asset.asset_key}
          </h1>
          {asset.artist && (
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{t("pages.asset.byArtist", { artist: asset.artist })}</span>
              {artistUrl && (
                <a
                  href={artistUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-primary underline-offset-4 hover:underline"
                >
                  [{t("pages.asset.artistHome")}]
                </a>
              )}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            <span className="rounded-md border border-border px-2 py-0.5">
              {asset.source}#{asset.source_id}
            </span>
            {hasMultiplePages && (
              <span className="rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 text-primary">
                {pages.length}P
              </span>
            )}
            {activeAsset?.page_index !== null && activeAsset?.page_index !== undefined && (
              <span className="rounded-md border border-border px-2 py-0.5">
                P{activeAsset.page_index + 1}
              </span>
            )}
            {activeAsset?.width && activeAsset.height && (
              <span className="rounded-md border border-border px-2 py-0.5">
                {activeAsset.width}×{activeAsset.height}
              </span>
            )}
            {asset.duplicate_of && (
              <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-500">
                {t("pages.asset.duplicateOf", { assetKey: asset.duplicate_of })}
              </span>
            )}
            {asset.deletion_status && (
              <span className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-destructive">
                {asset.deletion_status === "pending_cleanup" ? t("pages.asset.pendingCleanup") : asset.deletion_status}
                {asset.deleted_by_username && ` · by ${asset.deleted_by_username}`}
              </span>
            )}
          </div>
        </div>

        {hasMultiplePages && (
          <section className="space-y-2 rounded-lg border border-border bg-muted/25 p-3">
            <h2 className="text-sm font-medium">{t("pages.asset.pageDirectory")}</h2>
            <div className="grid max-h-72 grid-cols-4 gap-1 overflow-auto pr-1">
              {pages.map((page, index) => (
                <a
                  key={page.asset_key}
                  href={`#${encodeURIComponent(page.asset_key)}`}
                  className={cn(
                    "rounded-md border border-border bg-background px-2 py-1 text-center text-xs hover:bg-accent",
                    page.asset_key === activeAsset?.asset_key && "border-primary/50 bg-primary/10 text-primary"
                  )}
                  title={page.original_filename || page.asset_key}
                  onClick={() => setActiveAssetKey(page.asset_key)}
                >
                  {page.page_index !== null ? page.page_index + 1 : index + 1}
                </a>
              ))}
            </div>
          </section>
        )}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={downloadOriginal} disabled={downloading}>
            {downloading ? <Spinner className="h-4 w-4" /> : <Download className="h-4 w-4" />}
            {t("pages.asset.original")}
          </Button>
          {asset.original_url && (
            <Button asChild variant="outline" size="sm">
              <a href={asset.original_url} target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" /> {t("pages.asset.source")}
              </a>
            </Button>
          )}
          {artworkUrl && (
            <Button asChild variant="outline" size="sm">
              <a href={artworkUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" /> {t("pages.asset.artworkPage")}
              </a>
            </Button>
          )}
          {canDeleteRequest && !asset.deletion_status && (
            <Button
              variant="destructive"
              size="sm"
              onClick={requestDelete}
              disabled={deleting}
            >
              {deleting ? <Spinner className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
              {t("pages.asset.delete")}
            </Button>
          )}
          {canDelete && asset.deletion_status === "pending_cleanup" && (
            <Button
              variant="destructive"
              size="sm"
              onClick={purgeAsset}
              disabled={deleting}
            >
              {deleting ? <Spinner className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
              {t("pages.asset.purge")}
            </Button>
          )}
        </div>

        {asset.description && (
          <section className="space-y-2 rounded-lg border border-border bg-muted/25 p-3">
            <h2 className="text-sm font-medium">{t("pages.asset.description")}</h2>
            <p className="whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground">
              {asset.description}
            </p>
          </section>
        )}

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">{t("pages.asset.tags")}</h2>
            {token && !editing && (
              <Button variant="ghost" size="sm" onClick={startEdit}>
                <TagsIcon className="h-3.5 w-3.5" /> {t("pages.asset.edit")}
              </Button>
            )}
          </div>

          {editing ? (
            <div className="space-y-2">
              <textarea
                value={draftTags}
                onChange={(e) => setDraftTags(e.target.value)}
                rows={4}
                placeholder="character:misaka_mikoto series:toaru rating:safe"
                className="w-full rounded-md border border-input bg-transparent p-2 font-mono text-xs focus-ring"
              />
              <p className="text-[11px] text-muted-foreground">
                {t("pages.asset.editTagsHint")}
              </p>
              <div className="flex gap-2">
                <Button size="sm" onClick={saveTags} disabled={saving}>
                  {saving ? <Spinner className="h-3.5 w-3.5" /> : null} {t("common.save")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setEditing(false)}
                  disabled={saving}
                >
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {visibleTags.length === 0 && (
                <span className="text-xs text-muted-foreground">{t("pages.asset.untagged")}</span>
              )}
              {visibleTags.map((tag) => (
                <Link
                  key={tag}
                  href={`/?q=${encodeURIComponent(tag)}`}
                  className="rounded-full"
                >
                  <Badge variant={tagCategory(tag) as never} className="cursor-pointer">
                    <span className="opacity-60">{tagCategory(tag)}:</span>{" "}
                    {tagLabel(tag, tagDetails.get(tag)?.labels, locale)}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
        </section>

        {asset.pixiv_tags && asset.pixiv_tags.length > 0 && (
          <section>
            <h2 className="mb-2 text-sm font-medium">{t("pages.asset.sourceTags")}</h2>
            <div className="flex flex-wrap gap-1.5">
              {(asset.pixiv_tag_details?.length ? asset.pixiv_tag_details : asset.pixiv_tags.map((tag) => ({ name: tag, translated_name: null, source_tag: sourceTagQuery(tag) }))).map((tag) => {
                const query = tag.source_tag || sourceTagQuery(tag.name, tag.translated_name);
                const label = sourceTagLabel(tag.name, tag.translated_name, locale);
                const secondary = sourceTagSecondaryLabel(tag.name, tag.translated_name, locale);
                return (
                  <Link
                    key={tag.name}
                    href={`/?q=${encodeURIComponent(query)}`}
                    title={query}
                    className="rounded-full border border-dashed border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[11px] text-cyan-600 transition-colors hover:border-cyan-500/60 hover:bg-cyan-500/15 dark:text-cyan-400"
                  >
                    {label}
                    {secondary && <span className="ml-1 opacity-70">/ {secondary}</span>}
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        <ApiLinksSection
          asset={activeAsset ?? asset}
          pageLabel={hasMultiplePages ? `P${activePageIndex + 1} / ${pages.length}` : undefined}
        />

        <section className="space-y-1 text-xs text-muted-foreground">
          <div>
            asset_key:{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px] text-foreground">
              {activeAsset?.asset_key ?? asset.asset_key}
            </code>
          </div>
          <div className="break-all">
            sha256:{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px] text-foreground">
              {activeAsset?.source_file_sha256 ?? asset.source_file_sha256}
            </code>
          </div>
        </section>

        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          {t("common.refresh")}
        </Button>
      </aside>
    </div>
  );
}

type ApiLink = {
  label: string;
  hint: string;
  href: string;
  size?: number | null;
  filename?: string;
  needsAuth?: boolean;
  external?: boolean;
};

function AssetPageImage({
  asset,
  index,
  current,
}: {
  asset: Asset;
  index: number;
  current: boolean;
}) {
  const { t } = useI18n();
  const [loaded, setLoaded] = useState(false);
  const isGif = isAnimatedGifMedia(asset.source_type);
  return (
    <section
      id={asset.asset_key}
      className={cn(
        "scroll-mt-20 overflow-hidden rounded-xl border bg-card",
        current ? "border-primary/45 shadow-sm" : "border-border"
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2 text-xs">
        <div className="min-w-0 truncate text-muted-foreground">
          <span className="font-medium text-foreground">P{asset.page_index !== null ? asset.page_index + 1 : index + 1}</span>
          <span className="mx-1.5">·</span>
          <span title={asset.original_filename || asset.asset_key}>{asset.original_filename || asset.asset_key}</span>
        </div>
        {asset.width && asset.height && (
          <span className="shrink-0 text-muted-foreground">{asset.width}×{asset.height}</span>
        )}
      </div>
      <div className="relative bg-muted">
        {!loaded && (
          <div
            className="skeleton"
            style={{
              paddingTop: asset.width && asset.height
                ? `${(asset.height / asset.width) * 100}%`
                : "75%",
            }}
          />
        )}
        {isVideoMedia(asset.mime_type) ? (
          <video
            src={fileUrl.original(asset.asset_key)}
            controls={!isGif}
            autoPlay={isGif}
            loop={isGif}
            muted={isGif}
            playsInline
            preload={isGif ? "auto" : "metadata"}
            onLoadedMetadata={() => setLoaded(true)}
            onError={() => setLoaded(true)}
            className={cn(
              "h-auto w-full",
              isGif ? "bg-muted" : "bg-black",
              loaded ? "block" : "absolute inset-0 opacity-0"
            )}
          >
            {t("pages.asset.videoUnsupported")}
          </video>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={fileUrl.preview(asset.asset_key)}
            alt={asset.title || asset.asset_key}
            onLoad={() => setLoaded(true)}
            className={cn(
              "h-auto w-full bg-muted",
              loaded ? "block" : "absolute inset-0 opacity-0"
            )}
          />
        )}
      </div>
    </section>
  );
}

function ApiLinksSection({
  asset,
  pageLabel,
}: {
  asset: Asset;
  pageLabel?: string;
}) {
  const { locale, t } = useI18n();
  const assetKey = asset.asset_key;
  const links = useMemo<ApiLink[]>(() => {
    const items: ApiLink[] = [
      {
        label: t("pages.asset.apiJson"),
        hint: t("pages.asset.apiJsonHint"),
        href: `/api/assets/${encodeURIComponent(assetKey)}`,
      },
      {
        label: t("pages.asset.original"),
        hint: t("pages.asset.apiOriginalHint", { filename: asset.original_filename ? ` • ${asset.original_filename}` : "" }),
        href: fileUrl.original(assetKey),
        size: asset.file_size ?? null,
        filename: asset.original_filename || assetKey,
        needsAuth: true,
      },
      {
        label: t("pages.asset.apiPreview"),
        hint: t("pages.asset.apiPreviewHint"),
        href: asset.preview_url || fileUrl.preview(assetKey),
        size: asset.preview_file_size ?? null,
        filename: `${assetKey}-preview`,
      },
      {
        label: t("pages.asset.apiThumb"),
        hint: t("pages.asset.apiThumbHint"),
        href: asset.thumb_url || fileUrl.thumb(assetKey),
        size: asset.thumb_file_size ?? null,
        filename: `${assetKey}-thumb`,
      },
    ];
    if (asset.original_path) {
      items.push({
        label: t("pages.asset.apiStoragePath"),
        hint: t("pages.asset.apiStoragePathHint"),
        href: asset.original_path,
        external: false,
      });
    }
    return items;
  }, [asset, assetKey, t]);

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="text-sm font-medium">{t("pages.asset.resourceLinks")}</h2>
          {asset.crawl_time && (
            <span
              className="truncate text-[11px] font-normal text-muted-foreground"
              title={t("pages.asset.addedAt", { time: asset.crawl_time })}
            >
              {t("pages.asset.addedAt", { time: formatDateTime(asset.crawl_time, locale) })}
            </span>
          )}
        </div>
        {pageLabel && (
          <span className="rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
            {t("pages.asset.currentPage", { page: pageLabel })}
          </span>
        )}
      </div>
      <div className="space-y-1.5 rounded-lg border border-border bg-muted/30 p-2">
        {links.map((link) => (
          <ApiLinkRow key={link.label} {...link} />
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">
        {t("pages.asset.resourceLinksHint")}
      </p>
    </section>
  );
}

function ApiLinkRow({ label, hint, href, size, filename, needsAuth }: ApiLink) {
  const toast = useToast();
  const { token } = useAuth();
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [opening, setOpening] = useState(false);

  async function copy() {
    try {
      const absolute = href.startsWith("http")
        ? href
        : typeof window !== "undefined"
          ? `${window.location.origin}${href.startsWith("/") ? href : `/${href}`}`
          : href;
      await navigator.clipboard.writeText(absolute);
      setCopied(true);
      toast.success(t("common.copied"));
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t("pages.asset.copyFailed"));
    }
  }

  async function openInNewTab() {
    setOpening(true);
    const previewWindow = window.open("", "_blank");
    if (previewWindow) {
      previewWindow.opener = null;
      writeResourceWindow(previewWindow, label, `<main class="message">${escapeHtml(t("common.loading"))}</main>`);
    }
    try {
      const absolute = href.startsWith("http")
        ? href
        : `${window.location.origin}${href.startsWith("/") ? href : `/${href}`}`;
      const bearer = readToken();
      const res = await fetch(absolute, {
        headers: bearer ? { authorization: `Bearer ${bearer}` } : undefined,
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const responseFilename = filenameFromDisposition(res.headers.get("content-disposition"));
      await openBlobResource(blob, label, responseFilename || filename || label, previewWindow, {
        cannotPreview: t("pages.asset.fileCannotPreview"),
        downloadFile: t("pages.asset.downloadFile"),
      });
    } catch (e: unknown) {
      previewWindow?.close();
      toast.error(e instanceof Error ? e.message : t("pages.asset.openFailed"));
    } finally {
      setOpening(false);
    }
  }

  const isHttp = href.startsWith("/") || href.startsWith("http");
  const showOpen = isHttp && (!needsAuth || token);

  return (
    <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-background/60">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-foreground">
          <span className="font-medium">{label}</span>
          {size != null && (
            <span className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {formatBytes(size)}
            </span>
          )}
          {needsAuth && !token && (
            <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1 text-[10px] text-amber-500">
              {t("pages.asset.neededAuth")}
            </span>
          )}
        </div>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {hint}
        </div>
        <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground" title={href}>
          {href}
        </div>
      </div>
      <button
        type="button"
        onClick={copy}
        title={t("common.copyLink")}
        className="rounded-md border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      {showOpen && (
        <button
          type="button"
          onClick={openInNewTab}
          disabled={opening}
          title={t("common.openInNewTab")}
          className="rounded-md border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          {opening ? <Spinner className="h-3.5 w-3.5" /> : <ExternalLink className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}

function artistHomeUrl(asset: Asset): string | null {
  if (asset.source.toLowerCase() !== "pixiv") return null;
  const artistId = asset.artist_id.trim();
  return artistId ? `https://www.pixiv.net/users/${encodeURIComponent(artistId)}` : null;
}

function artworkHomeUrl(asset: Asset): string | null {
  switch (asset.source.toLowerCase()) {
    case "pixiv": {
      const sourceId = asset.source_id.trim();
      return sourceId ? `https://www.pixiv.net/artworks/${encodeURIComponent(sourceId)}` : null;
    }
    default:
      return null;
  }
}

function formatBytes(value: number | null | undefined): string {
  if (value == null) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index++;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function filenameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] ?? null;
}

async function openBlobResource(
  blob: Blob,
  title: string,
  filename: string,
  existingWindow: Window | null,
  messages: { cannotPreview: string; downloadFile: string },
): Promise<void> {
  const target = existingWindow ?? window.open("", "_blank");
  const objectUrl = URL.createObjectURL(blob);
  if (!target) {
    window.open(objectUrl, "_blank");
    return;
  }

  target.opener = null;
  const type = (blob.type || "application/octet-stream").toLowerCase();
  let body: string;
  if (type.startsWith("image/")) {
    body = `<main class="media"><img src="${escapeHtml(objectUrl)}" alt="${escapeHtml(filename)}" /></main>`;
  } else if (type.startsWith("video/")) {
    body = `<main class="media"><video src="${escapeHtml(objectUrl)}" controls autoplay loop></video></main>`;
  } else if (type.includes("json") || type.startsWith("text/")) {
    body = `<main class="text"><pre>${escapeHtml(await blob.text())}</pre></main>`;
  } else {
    body = `
      <main class="message">
        <h1>${escapeHtml(filename)}</h1>
        <p>${escapeHtml(messages.cannotPreview)}</p>
        <p class="meta">${escapeHtml(type)} · ${formatBytes(blob.size)}</p>
        <a href="${escapeHtml(objectUrl)}" download="${escapeHtml(filename)}">${escapeHtml(messages.downloadFile)}</a>
      </main>
    `;
  }
  writeResourceWindow(target, title, body);
}

function writeResourceWindow(target: Window, title: string, body: string): void {
  target.document.open();
  target.document.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root { color-scheme: dark light; }
    body {
      margin: 0;
      min-height: 100vh;
      background: #111;
      color: #f5f5f5;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .media {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 16px;
      box-sizing: border-box;
    }
    img, video {
      display: block;
      max-width: 100%;
      max-height: calc(100vh - 32px);
      object-fit: contain;
    }
    .text, .message {
      box-sizing: border-box;
      width: min(960px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
    }
    h1 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    p {
      color: #cfcfcf;
      line-height: 1.5;
    }
    .meta {
      font-size: 12px;
      color: #999;
    }
    a {
      color: #fff;
    }
  </style>
</head>
<body>${body}</body>
</html>`);
  target.document.close();
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      default:
        return "&#39;";
    }
  });
}
