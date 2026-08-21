"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, Heart, ImageOff, MessageCircle, Play, Repeat2, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/providers/locale-provider";
import type { Post, PostAttachment } from "@/lib/types";
import { cn, formatDateTime, formatNumber, isAnimatedGifMedia, isVideoMedia, truncate } from "@/lib/utils";

const MAX_VISIBLE_ATTACHMENTS = 4;

export function PostCard({ post }: { post: Post }) {
  const { locale, t } = useI18n();
  const [revealed, setRevealed] = useState(false);
  const hidden = Boolean(post.content_warning) && !revealed;
  const replies = post.metrics.replies ?? 0;
  const reposts = post.metrics.reposts ?? 0;
  const likes = post.metrics.likes ?? 0;

  return (
    <article className="rounded-xl border border-border bg-card p-4 shadow-sm transition-shadow hover:shadow-md">
      <header className="flex items-start gap-3">
        <PostAvatar post={post} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="truncate text-sm font-medium">{post.author_name || post.author_handle || post.author_id}</span>
            {post.author_handle && (
              <span className="truncate text-xs text-muted-foreground">@{truncate(post.author_handle, 32)}</span>
            )}
            <Badge variant="outline" className="shrink-0">{sourceLabel(post.source, t)}</Badge>
          </div>
          {post.posted_at && (
            <time className="mt-0.5 block text-xs text-muted-foreground" dateTime={post.posted_at} title={post.posted_at}>
              {formatPostedAt(post.posted_at)}
            </time>
          )}
        </div>
        {post.source_url && (
          <a
            href={post.source_url}
            target="_blank"
            rel="noreferrer"
            aria-label={t("pages.posts.viewSource")}
            title={t("pages.posts.viewSource")}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-border bg-muted/35 text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </header>

      {post.content_warning && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/35 px-3 py-2">
          <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600" />
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{post.content_warning}</span>
          <Button variant="outline" size="sm" onClick={() => setRevealed((value) => !value)}>
            {revealed ? t("pages.posts.hideContent") : t("pages.posts.showContent")}
          </Button>
        </div>
      )}

      {!hidden && (
        <>
          {post.content && (
            <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6">{post.content}</p>
          )}
          {post.attachments.length > 0 && <PostAttachments attachments={post.attachments} />}
        </>
      )}

      {post.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1">
          {post.tags.map((tag) => (
            <span
              key={tag}
              className="max-w-full truncate rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
              title={tag}
            >
              #{tag}
            </span>
          ))}
        </div>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-4 border-t border-border pt-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5" title={t("pages.posts.metrics.replies")}>
          <MessageCircle className="h-3.5 w-3.5" />
          {formatNumber(replies)}
        </span>
        <span className="inline-flex items-center gap-1.5" title={t("pages.posts.metrics.reposts")}>
          <Repeat2 className="h-3.5 w-3.5" />
          {formatNumber(reposts)}
        </span>
        <span className="inline-flex items-center gap-1.5" title={t("pages.posts.metrics.likes")}>
          <Heart className="h-3.5 w-3.5" />
          {formatNumber(likes)}
        </span>
        {post.attachment_count > 0 && (
          <span>{t("pages.posts.attachments", { count: post.attachment_count })}</span>
        )}
        {post.crawl_time && (
          <span className="ml-auto text-muted-foreground" title={post.crawl_time}>
            {t("pages.posts.addedAt", { time: formatDateTime(post.crawl_time, locale) })}
          </span>
        )}
        {post.source_url && (
          <a
            href={post.source_url}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "inline-flex items-center gap-1 underline-offset-4 transition-colors hover:text-foreground hover:underline",
              !post.crawl_time && "ml-auto"
            )}
          >
            {t("pages.posts.viewSource")}
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </footer>
    </article>
  );
}

export function PostCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full skeleton" />
        <div className="flex-1 space-y-1.5">
          <div className="h-3 w-1/4 rounded skeleton" />
          <div className="h-3 w-1/6 rounded skeleton" />
        </div>
      </div>
      <div className="mt-3 space-y-1.5">
        <div className="h-3 w-full rounded skeleton" />
        <div className="h-3 w-4/5 rounded skeleton" />
      </div>
      <div className="mt-3 h-40 rounded-lg skeleton" />
    </div>
  );
}

function PostAvatar({ post }: { post: Post }) {
  const [error, setError] = useState(false);
  const name = post.author_name || post.author_handle || post.author_id;
  if (post.author_avatar_url && !error) {
    return (
      <img
        src={post.author_avatar_url}
        alt={name}
        loading="lazy"
        decoding="async"
        onError={() => setError(true)}
        className="h-10 w-10 shrink-0 rounded-full object-cover"
      />
    );
  }
  return (
    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-muted text-sm font-medium text-muted-foreground">
      {initials(name)}
    </span>
  );
}

function PostAttachments({ attachments }: { attachments: PostAttachment[] }) {
  const visible = attachments.slice(0, MAX_VISIBLE_ATTACHMENTS);
  const overflow = attachments.length - visible.length;
  const single = visible.length === 1;

  return (
    <div
      className={cn(
        "mt-3 grid gap-1.5",
        single ? "grid-cols-1" : "grid-cols-2",
        visible.length === 3 && "grid-rows-2"
      )}
    >
      {visible.map((attachment, index) => (
        <PostAttachmentTile
          key={attachment.position}
          attachment={attachment}
          className={cn(
            single ? "aspect-[4/3] max-h-[26rem]" : "aspect-square",
            visible.length === 3 && index === 0 && "row-span-2 aspect-auto"
          )}
          overflow={overflow > 0 && index === visible.length - 1 ? overflow : 0}
        />
      ))}
    </div>
  );
}

function PostAttachmentTile({
  attachment,
  className,
  overflow,
}: {
  attachment: PostAttachment;
  className?: string;
  overflow: number;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const isVideo = isVideoMedia(attachment.mime_type);
  const isGif = isAnimatedGifMedia(attachment.source_type);
  const videoSrc = isVideo && attachment.asset_key && attachment.asset_available
    ? `/api/assets/${encodeURIComponent(attachment.asset_key)}/original${isGif ? "" : "#t=0.1"}`
    : isVideo
      ? attachment.remote_url
      : "";
  const src = attachment.thumb_url || attachment.preview_url || attachment.remote_url;
  const alt = attachment.description || attachment.asset_key || "";

  const body = (
    <div className={cn("relative overflow-hidden rounded-lg bg-muted", className)}>
      {isVideo && videoSrc && !error ? (
        <video
          src={videoSrc}
          autoPlay={isGif}
          loop={isGif}
          muted
          playsInline
          preload={isGif ? "auto" : "metadata"}
          onLoadedData={() => setLoaded(true)}
          onError={() => setError(true)}
          className={cn(
            "absolute inset-0 h-full w-full object-cover transition-opacity duration-500",
            loaded ? "opacity-100" : "opacity-0"
          )}
        />
      ) : src && !error ? (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
          className={cn(
            "absolute inset-0 h-full w-full object-cover transition-opacity duration-500",
            loaded ? "opacity-100" : "opacity-0"
          )}
        />
      ) : (
        <div className="absolute inset-0 grid place-items-center text-muted-foreground">
          <ImageOff className="h-6 w-6" />
        </div>
      )}
      {(src || videoSrc) && !loaded && !error && <div className="absolute inset-0 skeleton" />}
      {isVideo && !isGif && !error && overflow === 0 && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-black/55 text-white shadow-lg backdrop-blur-sm">
            <Play className="h-4 w-4 translate-x-[1px] fill-current" />
          </span>
        </div>
      )}
      {isGif && !error && overflow === 0 && (
        <div className="pointer-events-none absolute left-1.5 top-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white backdrop-blur-sm">
          GIF
        </div>
      )}
      {overflow > 0 && (
        <div className="absolute inset-0 grid place-items-center bg-black/55 text-sm font-medium text-white">
          +{overflow}
        </div>
      )}
    </div>
  );

  if (attachment.asset_key && attachment.asset_available) {
    return (
      <Link href={`/asset/${encodeURIComponent(attachment.asset_key)}`} prefetch={false} className="block">
        {body}
      </Link>
    );
  }
  if (attachment.remote_url) {
    return (
      <a href={attachment.remote_url} target="_blank" rel="noreferrer" className="block">
        {body}
      </a>
    );
  }
  return body;
}

function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return Array.from(trimmed)[0].toUpperCase();
}

function sourceLabel(source: string, t: (key: string) => string): string {
  const label = t(`pages.posts.sources.${source}`);
  return label === `pages.posts.sources.${source}` ? source : label;
}

function formatPostedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
