"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import {
  CheckCircle2,
  FilePlus2,
  ImageIcon,
  Loader2,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { formatUploadBytes, useUploadQueue } from "@/hooks/upload/use-upload-queue";
import { cn } from "@/lib/utils";
import { TagChipInput } from "@/components/ui/tag-chip-input";

const ACCEPT = "image/*,.zip";

export default function UploadPage() {
  const router = useRouter();
  const { token, ready } = useAuth();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    items,
    generateCache,
    setGenerateCache,
    defaultArtist,
    setDefaultArtist,
    defaultTags,
    setDefaultTags,
    tagAliasesText,
    setTagAliasesText,
    storageStrategy,
    setStorageStrategy,
    storageStrategies,
    loadStorageStrategies,
    submitting,
    dragActive,
    setDragActive,
    stats,
    addFiles,
    updateItem,
    removeItem,
    clearAll,
    uploadAll,
  } = useUploadQueue({ onSuccess: toast.success, onError: toast.error });

  useEffect(() => {
    if (!ready || !token) return;
    void loadStorageStrategies();
  }, [loadStorageStrategies, ready, token]);

  if (ready && !token) {
    return (
      <div className="container max-w-md py-16 text-center">
        <h1 className="mb-2 text-lg font-semibold">需要登录</h1>
        <p className="text-sm text-muted-foreground">
          上传需要 editor、admin 或 developer 权限。
        </p>
        <Button className="mt-4" onClick={() => router.push("/login")}>
          去登录
        </Button>
      </div>
    );
  }

  return (
    <div className="container max-w-4xl py-8 pb-32">
      <div className="mb-6 flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-primary to-fuchsia-500 text-primary-foreground">
          <UploadCloud className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold">上传作品</h1>
          <p className="text-xs text-muted-foreground">
            支持多文件、累加添加。原始字节不会被修改，仅生成 AVIF / WEBP 缓存。
          </p>
        </div>
      </div>

      {/* Drop zone / picker */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          if (e.dataTransfer?.files) addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "relative flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-8 text-center transition-colors",
          dragActive
            ? "border-primary bg-primary/5"
            : "border-border bg-card hover:bg-muted/40"
        )}
      >
        <span className="grid h-12 w-12 place-items-center rounded-full bg-muted text-muted-foreground">
          <FilePlus2 className="h-6 w-6" />
        </span>
        <p className="text-sm">
          拖拽图片到这里，或者
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="ml-1 font-medium text-primary hover:underline"
          >
            从资源管理器选择
          </button>
        </p>
        <p className="text-xs text-muted-foreground">
          支持多选，可以多次添加，文件按所选顺序上传
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {/* Default fields */}
      <div className="mt-5 grid gap-4 rounded-2xl border border-border bg-card p-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="storage_strategy">Storage strategy</Label>
          <select
            id="storage_strategy"
            value={storageStrategy}
            onChange={(e) => setStorageStrategy(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
          >
            {storageStrategies.map((strategy) => (
              <option key={strategy.name} value={strategy.name}>
                {strategy.name}{strategy.is_default ? " (default)" : ""} · {strategy.type}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="default_artist">默认作者</Label>
          <Input
            id="default_artist"
            value={defaultArtist}
            onChange={(e) => setDefaultArtist(e.target.value)}
            placeholder="留空，单条目可单独覆盖"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label>默认标签</Label>
          <TagChipInput
            tags={defaultTags}
            onChange={setDefaultTags}
            placeholder="输入标签后回车，应用到所有条目"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-3">
          <Label htmlFor="tag_aliases">标签别名</Label>
          <textarea
            id="tag_aliases"
            value={tagAliasesText}
            onChange={(e) => setTagAliasesText(e.target.value)}
            rows={3}
            placeholder={"character:misaka_mikoto = 御坂美琴, 美琴\n超电磁炮 -> series:toaru"}
            className="w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs outline-none focus-ring"
          />
        </div>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            checked={generateCache}
            onChange={(e) => setGenerateCache(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
          />
          上传后立即生成预览缓存
        </label>
      </div>

      {/* List */}
      <div className="mt-5 space-y-3">
        {items.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
            还没有文件，先添加几个吧
          </div>
        )}
        {items.map((item, idx) => (
          <div
            key={item.id}
            className={cn(
              "flex flex-col gap-3 rounded-xl border bg-card p-3 sm:flex-row sm:items-start",
              item.status === "done" && "border-emerald-500/30",
              item.status === "error" && "border-destructive/40"
            )}
          >
            <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-md border border-border bg-muted">
              {item.preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={item.preview}
                  alt={item.file.name}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                  <ImageIcon className="h-6 w-6" />
                </div>
              )}
              <span className="absolute left-1 top-1 rounded bg-background/80 px-1 text-[10px] font-medium">
                {idx + 1}
              </span>
            </div>

            <div className="grid flex-1 gap-2 sm:grid-cols-3">
              <div className="space-y-1 sm:col-span-3">
                <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span className="truncate font-medium text-foreground" title={item.file.name}>
                    {item.file.name}
                  </span>
                  <span className="shrink-0">{formatUploadBytes(item.file.size)}</span>
                </div>
                {item.message && (
                  <p
                    className={cn(
                      "text-[11px]",
                      item.status === "error" && "text-destructive",
                      item.status === "done" && "text-emerald-600 dark:text-emerald-400"
                    )}
                  >
                    {item.message}
                    {item.status === "done" && item.assetKey && (
                      <a
                        href={`/asset/${encodeURIComponent(item.assetKey)}`}
                        className="ml-2 underline hover:text-primary"
                      >
                        查看
                      </a>
                    )}
                  </p>
                )}
              </div>

              <div>
                <Label className="text-[11px]">标题</Label>
                <Input
                  value={item.title}
                  onChange={(e) => updateItem(item.id, { title: e.target.value })}
                  className="h-8"
                  disabled={item.status === "uploading"}
                />
              </div>
              <div>
                <Label className="text-[11px]">作者</Label>
                <Input
                  value={item.artist}
                  onChange={(e) => updateItem(item.id, { artist: e.target.value })}
                  placeholder={defaultArtist || "可选"}
                  className="h-8"
                  disabled={item.status === "uploading"}
                />
              </div>
              <div>
                <Label className="text-[11px]">Source ID</Label>
                <Input
                  value={item.sourceId}
                  onChange={(e) => updateItem(item.id, { sourceId: e.target.value })}
                  placeholder="留空使用 SHA256 前缀"
                  className="h-8"
                  disabled={item.status === "uploading"}
                />
              </div>
              <div className="sm:col-span-3">
                <Label className="text-[11px]">标签</Label>
                <TagChipInput
                  tags={item.tags}
                  onChange={(tags) => updateItem(item.id, { tags })}
                  placeholder="输入标签后回车"
                  disabled={item.status === "uploading"}
                  small
                />
              </div>
            </div>

            <div className="flex flex-col items-end gap-2">
              <div
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
                  item.status === "pending" && "border-border text-muted-foreground",
                  item.status === "uploading" && "border-primary/40 text-primary",
                  item.status === "done" &&
                    "border-emerald-500/40 text-emerald-600 dark:text-emerald-400",
                  item.status === "error" && "border-destructive/40 text-destructive"
                )}
              >
                {item.status === "uploading" && <Loader2 className="h-3 w-3 animate-spin" />}
                {item.status === "done" && <CheckCircle2 className="h-3 w-3" />}
                {item.status === "error" && <XCircle className="h-3 w-3" />}
                {item.status === "pending" && "待上传"}
                {item.status === "uploading" && "上传中"}
                {item.status === "done" && "已完成"}
                {item.status === "error" && "失败"}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeItem(item.id)}
                disabled={item.status === "uploading"}
                aria-label="移除"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Sticky bottom action bar */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/90 backdrop-blur">
        <div className="container flex flex-wrap items-center gap-3 py-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span>
              共 <span className="font-medium text-foreground">{stats.total}</span> 个 ·{" "}
              {formatUploadBytes(stats.bytes)}
            </span>
            {stats.pending > 0 && <span>待 {stats.pending}</span>}
            {stats.done > 0 && (
              <span className="text-emerald-600 dark:text-emerald-400">完成 {stats.done}</span>
            )}
            {stats.errored > 0 && (
              <span className="text-destructive">失败 {stats.errored}</span>
            )}
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => inputRef.current?.click()}
              disabled={submitting}
            >
              <FilePlus2 className="h-4 w-4" /> 继续添加
            </Button>
            {stats.done > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => clearAll("done")}
                disabled={submitting}
              >
                清除已完成
              </Button>
            )}
            {items.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => clearAll("all")}
                disabled={submitting}
              >
                <Trash2 className="h-4 w-4" /> 清空
              </Button>
            )}
            <Button onClick={uploadAll} disabled={submitting || stats.pending + stats.errored === 0}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> 上传中
                </>
              ) : (
                <>
                  <UploadCloud className="h-4 w-4" />
                  开始上传
                  {stats.pending + stats.errored > 0 && (
                    <span className="ml-1 rounded-full bg-primary-foreground/20 px-1.5 text-[11px]">
                      {stats.pending + stats.errored}
                    </span>
                  )}
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
