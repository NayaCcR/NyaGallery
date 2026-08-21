"use client";

import Link from "next/link";
import { useState } from "react";
import { ImageOff, Play } from "lucide-react";
import type { Asset } from "@/lib/types";
import { fileUrl } from "@/lib/api";
import { cn, isAnimatedGifMedia, isHiddenTag, isTechnicalTag, isVideoMedia, tagCategory, tagLabel, truncate } from "@/lib/utils";
import { useI18n } from "@/components/providers/locale-provider";

const PLACEHOLDER_RATIO = 1.4;

export function AssetCard({
  asset,
  activeTags = [],
  onTagClick,
  href,
  groupCount,
  groupLabel,
}: {
  asset: Asset;
  activeTags?: string[];
  onTagClick?: (tag: string) => void;
  href?: string;
  groupCount?: number;
  groupLabel?: string;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const { locale, t } = useI18n();

  const ratio =
    asset.width && asset.height ? asset.height / asset.width : PLACEHOLDER_RATIO;
  const paddingTop = `${(ratio * 100).toFixed(2)}%`;

  const isVideo = isVideoMedia(asset.mime_type);
  const isGif = isAnimatedGifMedia(asset.source_type);
  const previewTags = asset.tags.filter((tag) => !isHiddenTag(tag) && !isTechnicalTag(tag)).slice(0, 3);
  const characterTag = asset.tags.find((tag) => tag.startsWith("character:"));
  const seriesTag = asset.tags.find((tag) => tag.startsWith("series:"));
  const tagDetails = new Map((asset.tag_details ?? []).map((tag) => [tag.name, tag]));

  return (
    <article className="group relative overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg">
      <Link
        href={href ?? `/asset/${encodeURIComponent(asset.asset_key)}`}
        className="block"
        prefetch={false}
      >
        <div
          className="relative w-full overflow-hidden bg-muted"
          style={{ paddingTop }}
        >
          {isVideo ? (
            <video
              src={isGif ? fileUrl.original(asset.asset_key) : `${fileUrl.original(asset.asset_key)}#t=0.1`}
              autoPlay={isGif}
              loop={isGif}
              muted
              playsInline
              preload={isGif ? "auto" : "metadata"}
              onLoadedData={() => setLoaded(true)}
              onError={() => setError(true)}
              className={cn(
                "absolute inset-0 h-full w-full object-cover transition-all duration-500 group-hover:scale-[1.03]",
                loaded ? "opacity-100" : "opacity-0"
              )}
            />
          ) : !error ? (
            <img
              src={fileUrl.preview(asset.asset_key)}
              alt={asset.title || asset.asset_key}
              loading="lazy"
              decoding="async"
              onLoad={() => setLoaded(true)}
              onError={() => setError(true)}
              className={cn(
                "absolute inset-0 h-full w-full object-cover transition-all duration-500 group-hover:scale-[1.03]",
                loaded ? "opacity-100" : "opacity-0"
              )}
            />
          ) : (
            <div className="absolute inset-0 grid place-items-center text-muted-foreground">
              <ImageOff className="h-6 w-6" />
            </div>
          )}
          {!loaded && !error && <div className="absolute inset-0 skeleton" />}

          {isVideo && !error && !isGif && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-black/55 text-white shadow-lg backdrop-blur-sm transition-transform duration-200 group-hover:scale-110">
                <Play className="h-5 w-5 translate-x-[1px] fill-current" />
              </span>
            </div>
          )}
          {isGif && !error && (
            <div className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white backdrop-blur-sm">
              GIF
            </div>
          )}

          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent p-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <div className="text-xs font-medium text-white/90 line-clamp-2">
              {asset.title || asset.asset_key}
            </div>
            {asset.artist && (
              <div className="mt-0.5 text-[11px] text-white/70">
                @ {truncate(asset.artist, 22)}
              </div>
            )}
          </div>

          <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
            {groupCount && groupCount > 1 && (
              <div
                className="rounded-full bg-primary/90 px-2 py-0.5 text-[10px] font-medium text-primary-foreground shadow"
                title={groupLabel}
              >
                {groupCount}P
              </div>
            )}
            {asset.duplicate_of && (
              <div className="rounded-full bg-amber-500/90 px-2 py-0.5 text-[10px] font-medium text-white shadow">
                DUP
              </div>
            )}
            {asset.deletion_status && (
              <div className="rounded-full bg-destructive/90 px-2 py-0.5 text-[10px] font-medium text-white shadow">
                {asset.deletion_status === "pending_cleanup" ? t("pages.asset.pendingCleanup") : asset.deletion_status}
              </div>
            )}
          </div>
        </div>
      </Link>

      <div className="flex flex-wrap items-center gap-1 px-2 py-1.5">
        {previewTags.map((tag) => {
          const active = activeTags.includes(tag);
          return (
            <button
              key={tag}
              type="button"
              onClick={(e) => {
                e.preventDefault();
                onTagClick?.(tag);
              }}
              className={cn(
                "max-w-full truncate rounded-full border px-2 py-0.5 text-[10px] transition-colors",
                "hover:bg-accent",
                active
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-muted text-muted-foreground"
              )}
              title={tag}
            >
              <span className="opacity-60">{tagCategory(tag)}:</span>{" "}
              {tagLabel(tag, tagDetails.get(tag)?.labels, locale)}
            </button>
          );
        })}
        {(characterTag || seriesTag) && previewTags.length === 0 && (
          <span className="text-[10px] text-muted-foreground">
            {characterTag
              ? tagLabel(characterTag, tagDetails.get(characterTag)?.labels, locale)
              : tagLabel(seriesTag!, tagDetails.get(seriesTag!)?.labels, locale)}
          </span>
        )}
      </div>
    </article>
  );
}

export function AssetCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div
        className="skeleton"
        style={{ paddingTop: `${PLACEHOLDER_RATIO * 100}%` }}
      />
      <div className="space-y-1.5 p-2">
        <div className="h-3 w-1/2 rounded skeleton" />
        <div className="h-3 w-1/3 rounded skeleton" />
      </div>
    </div>
  );
}
