"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  FilePlus2,
  ImageIcon,
  Loader2,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TagChipInput } from "@/components/ui/tag-chip-input";
import { formatUploadBytes, useUploadQueue } from "@/hooks/upload/use-upload-queue";
import { ApiError, NyaApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACCEPT = "image/*,.zip";
type DirectoryEntry = FileSystemEntry & { createReader: () => FileSystemDirectoryReader };
type FileEntry = FileSystemFileEntry;

export default function UploadPage() {
  const router = useRouter();
  const { token, ready } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [remoteUrls, setRemoteUrls] = useState("");
  const [remoteBusy, setRemoteBusy] = useState(false);
  const [remoteFailures, setRemoteFailures] = useState<string[]>([]);
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
    chunkSizeMiB,
    setChunkSizeMiB,
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

  useEffect(() => {
    if (!ready || !token) return;
    const handlePaste = (event: ClipboardEvent) => {
      const imageFiles = Array.from(event.clipboardData?.files ?? []).filter((file) => file.type.startsWith("image/"));
      if (imageFiles.length > 0) {
        event.preventDefault();
        addFiles(imageFiles);
        return;
      }
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, [contenteditable='true']")) return;
      const text = event.clipboardData?.getData("text/plain") ?? "";
      const urls = text.split(/[\s,]+/).filter((value) => /^https?:\/\//i.test(value));
      if (urls.length > 0) {
        event.preventDefault();
        setRemoteUrls((current) => [current.trim(), ...urls].filter(Boolean).join("\n"));
      }
    };
    window.addEventListener("paste", handlePaste);
    return () => window.removeEventListener("paste", handlePaste);
  }, [addFiles, ready, token]);

  async function addDroppedFiles(dataTransfer: DataTransfer) {
    const entries = Array.from(dataTransfer.items ?? [])
      .map((item) => (item as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntry | null }).webkitGetAsEntry?.())
      .filter((entry): entry is FileSystemEntry => Boolean(entry));
    if (entries.length === 0) {
      if (dataTransfer.files.length > 0) addFiles(dataTransfer.files);
      return;
    }
    const files: File[] = [];
    for (const entry of entries) await collectDroppedEntry(entry, files);
    addFiles(files);
  }

  async function uploadRemoteUrls() {
    const urls = remoteUrls.split(/[\s,]+/).map((value) => value.trim()).filter(Boolean);
    if (urls.length === 0) {
      toast.error(t("pages.upload.remoteUrlRequired"));
      return;
    }
    setRemoteBusy(true);
    const failures: string[] = [];
    for (const url of urls) {
      try {
        await NyaApi.uploadRemote({ url, generate_cache: generateCache, storage_strategy: storageStrategy });
      } catch (error) {
        failures.push(`${url}: ${error instanceof ApiError ? error.message : String(error)}`);
      }
    }
    setRemoteFailures(failures);
    setRemoteUrls(failures.map((failure) => failure.split(": ", 1)[0]).join("\n"));
    setRemoteBusy(false);
    if (failures.length === 0) toast.success(t("pages.upload.remoteSuccess", { count: urls.length }));
    else toast.error(t("pages.upload.remotePartial", { count: failures.length }));
  }

  if (ready && !token) {
    return (
      <div className="container max-w-md py-16 text-center">
        <h1 className="mb-2 text-lg font-semibold">{t("common.loginRequired")}</h1>
        <p className="text-sm text-muted-foreground">{t("pages.upload.loginDescription")}</p>
        <Button className="mt-4" onClick={() => router.push("/login")}>
          {t("auth.goLogin")}
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
          <h1 className="text-xl font-semibold">{t("pages.upload.title")}</h1>
          <p className="text-xs text-muted-foreground">{t("pages.upload.description")}</p>
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          void addDroppedFiles(e.dataTransfer);
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
          {t("pages.upload.dropText")}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="ml-1 font-medium text-primary hover:underline"
          >
            {t("pages.upload.pickFiles")}
          </button>
        </p>
        <p className="text-xs text-muted-foreground">{t("pages.upload.dragHint")}</p>
        <p className="text-xs text-muted-foreground">{t("pages.upload.pasteHint")}</p>
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

      <div className="mt-4 space-y-3 rounded-2xl border border-border bg-card p-4">
        <div>
          <Label htmlFor="remote_urls">{t("pages.upload.remoteUrls")}</Label>
          <p className="mt-1 text-xs text-muted-foreground">{t("pages.upload.remoteUrlsHint")}</p>
        </div>
        <textarea
          id="remote_urls"
          value={remoteUrls}
          onChange={(event) => setRemoteUrls(event.target.value)}
          rows={3}
          placeholder="https://example.com/image.jpg"
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-ring"
          disabled={remoteBusy}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={uploadRemoteUrls} disabled={remoteBusy}>
            {remoteBusy && <Loader2 className="h-4 w-4 animate-spin" />}
            {t("pages.upload.remoteUpload")}
          </Button>
          {remoteFailures.length > 0 && <span className="text-xs text-destructive">{t("pages.upload.remoteFailures", { count: remoteFailures.length })}</span>}
        </div>
      </div>

      <div className="mt-5 grid gap-4 rounded-2xl border border-border bg-card p-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="chunk_size">{t("pages.upload.chunkSize", { size: chunkSizeMiB })}</Label>
          <input id="chunk_size" type="range" min={1} max={32} step={1} value={chunkSizeMiB} onChange={(event) => setChunkSizeMiB(Number(event.target.value))} className="h-9 w-full accent-[hsl(var(--primary))]" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="storage_strategy">{t("pages.upload.storageStrategy")}</Label>
          <select
            id="storage_strategy"
            value={storageStrategy}
            onChange={(e) => setStorageStrategy(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
          >
            {storageStrategies.map((strategy) => (
              <option key={strategy.name} value={strategy.name}>
                {strategy.name}{strategy.is_default ? ` (${t("common.defaultOption")})` : ""} · {strategy.type}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="default_artist">{t("pages.upload.defaultArtist")}</Label>
          <Input
            id="default_artist"
            value={defaultArtist}
            onChange={(e) => setDefaultArtist(e.target.value)}
            placeholder={t("pages.upload.defaultArtistPlaceholder")}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label>{t("pages.upload.defaultTags")}</Label>
          <TagChipInput
            tags={defaultTags}
            onChange={setDefaultTags}
            placeholder={t("pages.upload.defaultTagsPlaceholder")}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-3">
          <Label htmlFor="tag_aliases">{t("pages.upload.tagAliases")}</Label>
          <textarea
            id="tag_aliases"
            value={tagAliasesText}
            onChange={(e) => setTagAliasesText(e.target.value)}
            rows={3}
            placeholder={t("pages.upload.tagAliasesPlaceholder")}
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
          {t("pages.upload.generateCache")}
        </label>
      </div>

      <div className="mt-5 space-y-3">
        {items.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
            {t("pages.upload.empty")}
          </div>
        )}
        {items.map((item, idx) => (
          <details key={item.id} className={cn("group rounded-xl border bg-card", item.status === "done" && "border-emerald-500/30", item.status === "error" && "border-destructive/40")}>
            <summary className="flex cursor-pointer list-none items-center gap-3 p-3 marker:hidden [&::-webkit-details-marker]:hidden">
              <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-md border border-border bg-muted">
                {item.preview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.preview} alt="" loading="lazy" className="h-full w-full object-cover" />
                ) : <div className="flex h-full w-full items-center justify-center text-muted-foreground"><ImageIcon className="h-5 w-5" /></div>}
                <span className="absolute left-1 top-1 rounded bg-background/80 px-1 text-[10px] font-medium">{idx + 1}</span>
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate font-medium" title={item.file.name}>{item.file.name}</span>
                  <span className="shrink-0 text-muted-foreground">{formatUploadBytes(item.file.size)}</span>
                </div>
                {item.status === "uploading" && typeof item.progress === "number" && <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-[width]" style={{ width: `${item.progress}%` }} /></div>}
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className={cn(item.status === "done" && "text-emerald-600 dark:text-emerald-400", item.status === "error" && "text-destructive")}>{t(`pages.upload.${item.status}`)}</span>
                  {item.message && <span className="truncate">{item.message}</span>}
                </div>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground transition-transform group-open:rotate-180">⌄</span>
              <Button type="button" variant="ghost" size="sm" className="shrink-0" onClick={(event) => { event.preventDefault(); removeItem(item.id); }} disabled={item.status === "uploading"} aria-label={t("pages.upload.clear")}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </summary>
            <div className="grid gap-2 border-t border-border p-3 sm:grid-cols-3">
              {item.message && <p className={cn("text-[11px] sm:col-span-3", item.status === "error" && "text-destructive", item.status === "done" && "text-emerald-600 dark:text-emerald-400")}>
                {item.message}
                {item.status === "done" && item.assetKey && <a href={`/asset/${encodeURIComponent(item.assetKey)}`} className="ml-2 underline hover:text-primary">{t("pages.upload.view")}</a>}
              </p>}
              <div><Label className="text-[11px]">{t("pages.upload.titleField")}</Label><Input value={item.title} onChange={(e) => updateItem(item.id, { title: e.target.value })} className="h-8" disabled={item.status === "uploading"} /></div>
              <div><Label className="text-[11px]">{t("pages.upload.defaultArtist")}</Label><Input value={item.artist} onChange={(e) => updateItem(item.id, { artist: e.target.value })} placeholder={defaultArtist || t("pages.upload.defaultArtistPlaceholder")} className="h-8" disabled={item.status === "uploading"} /></div>
              <div><Label className="text-[11px]">Source ID</Label><Input value={item.sourceId} onChange={(e) => updateItem(item.id, { sourceId: e.target.value })} placeholder={t("pages.upload.sourceIdPlaceholder")} className="h-8" disabled={item.status === "uploading"} /></div>
              <div className="sm:col-span-3"><Label className="text-[11px]">{t("pages.upload.tags")}</Label><TagChipInput tags={item.tags} onChange={(tags) => updateItem(item.id, { tags })} placeholder={t("pages.upload.tagsPlaceholder")} disabled={item.status === "uploading"} small /></div>
              <div className="flex items-center gap-3 border-t border-border pt-3 text-xs sm:col-span-3">
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={item.flipHorizontal} disabled={item.status === "uploading"} onChange={(event) => updateItem(item.id, { flipHorizontal: event.target.checked })} />{t("pages.upload.flipHorizontal")}</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={item.flipVertical} disabled={item.status === "uploading"} onChange={(event) => updateItem(item.id, { flipVertical: event.target.checked })} />{t("pages.upload.flipVertical")}</label>
                <select aria-label={t("pages.upload.duplicateStrategy")} value={item.duplicateStrategy} disabled={item.status === "uploading"} onChange={(event) => updateItem(item.id, { duplicateStrategy: event.target.value as "skip" | "overwrite" | "keep" })} className="h-8 rounded-md border border-input bg-background px-2 text-xs"><option value="keep">{t("pages.upload.duplicateKeep")}</option><option value="skip">{t("pages.upload.duplicateSkip")}</option><option value="overwrite">{t("pages.upload.duplicateOverwrite")}</option></select>
                <select aria-label={t("pages.upload.exifPolicy")} value={item.exifPolicy} disabled={item.status === "uploading"} onChange={(event) => updateItem(item.id, { exifPolicy: event.target.value as "keep" | "strip" })} className="h-8 rounded-md border border-input bg-background px-2 text-xs"><option value="keep">{t("pages.upload.exifKeep")}</option><option value="strip">{t("pages.upload.exifStrip")}</option></select>
              </div>
            </div>
          </details>
        ))}
      </div>
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/90 backdrop-blur">
        <div className="container flex flex-wrap items-center gap-3 py-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span>
              {t("common.all")} <span className="font-medium text-foreground">{stats.total}</span> ·{" "}
              {formatUploadBytes(stats.bytes)}
            </span>
            {stats.pending > 0 && <span>{t("pages.upload.pending")} {stats.pending}</span>}
            {stats.done > 0 && (
              <span className="text-emerald-600 dark:text-emerald-400">{t("pages.upload.done")} {stats.done}</span>
            )}
            {stats.errored > 0 && (
              <span className="text-destructive">{t("pages.upload.error")} {stats.errored}</span>
            )}
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => inputRef.current?.click()}
              disabled={submitting}
            >
              <FilePlus2 className="h-4 w-4" /> {t("pages.upload.addMore")}
            </Button>
            {stats.done > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => clearAll("done")}
                disabled={submitting}
              >
                {t("pages.upload.clearDone")}
              </Button>
            )}
            {items.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => clearAll("all")}
                disabled={submitting}
              >
                <Trash2 className="h-4 w-4" /> {t("pages.upload.clear")}
              </Button>
            )}
            <Button onClick={uploadAll} disabled={submitting || stats.pending + stats.errored === 0}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> {t("pages.upload.uploading")}
                </>
              ) : (
                <>
                  <UploadCloud className="h-4 w-4" />
                  {t("pages.upload.start")}
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

async function collectDroppedEntry(entry: FileSystemEntry, files: File[]): Promise<void> {
  if (entry.isFile) {
    await new Promise<void>((resolve) => (entry as FileEntry).file((file) => { files.push(file); resolve(); }, () => resolve()));
    return;
  }
  const reader = (entry as DirectoryEntry).createReader();
  while (true) {
    const batch = await new Promise<FileSystemEntry[]>((resolve) => reader.readEntries(resolve, () => resolve([])));
    if (batch.length === 0) break;
    for (const child of batch) await collectDroppedEntry(child, files);
  }
}
