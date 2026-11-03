"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { StorageStrategySummary } from "@/lib/types";
import { uploadResumeStore } from "@/lib/upload-resume";

export type UploadStatus = "pending" | "uploading" | "done" | "error";

export type UploadItem = {
  id: string;
  file: File;
  preview: string | null;
  title: string;
  artist: string;
  sourceId: string;
  tags: string[];
  status: UploadStatus;
  progress?: number;
  message?: string;
  assetKey?: string;
  resumeUploadId?: string;
  rotation: 0 | 90 | 180 | 270;
  cropLeft: number;
  cropTop: number;
  cropRight: number;
  cropBottom: number;
  flipHorizontal: boolean;
  flipVertical: boolean;
  exifPolicy: "keep" | "strip";
};

type UseUploadQueueOptions = {
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
};

const LOCAL_STORAGE_STRATEGY: StorageStrategySummary = {
  name: "local",
  type: "local",
  is_default: true,
  is_remote: false,
};

export function formatUploadBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function useUploadQueue({ onSuccess, onError }: UseUploadQueueOptions) {
  const { t } = useI18n();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [generateCache, setGenerateCache] = useState(false);
  const [defaultArtist, setDefaultArtist] = useState("");
  const [defaultTags, setDefaultTags] = useState<string[]>([]);
  const [tagAliasesText, setTagAliasesText] = useState("");
  const [storageStrategy, setStorageStrategy] = useState("local");
  const [storageStrategies, setStorageStrategies] = useState<StorageStrategySummary[]>([LOCAL_STORAGE_STRATEGY]);
  const [submitting, setSubmitting] = useState(false);
  const [chunkSizeMiB, setChunkSizeMiBState] = useState(8);
  const [resumeLoaded, setResumeLoaded] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const itemsRef = useRef<UploadItem[]>([]);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    const savedSize = Number(localStorage.getItem("nya.upload.chunk-size-mib"));
    if (Number.isInteger(savedSize) && savedSize >= 1 && savedSize <= 32) setChunkSizeMiBState(savedSize);
    void uploadResumeStore.list().then((saved) => {
      if (saved.length === 0) {
        setResumeLoaded(true);
        return;
      }
      setItems((current) => {
        const existing = new Set(current.map((item) => item.id));
        const restored = saved.filter((entry) => !existing.has(entry.id)).map((entry) => ({
          id: entry.id,
          file: entry.file,
          title: entry.title,
          artist: entry.artist,
          sourceId: entry.sourceId,
          tags: entry.tags,
          resumeUploadId: entry.uploadId,
          rotation: entry.rotation ?? 0,
          cropLeft: entry.cropLeft ?? 0,
          cropTop: entry.cropTop ?? 0,
          cropRight: entry.cropRight ?? 0,
          cropBottom: entry.cropBottom ?? 0,
          flipHorizontal: entry.flipHorizontal ?? false,
          flipVertical: entry.flipVertical ?? false,
          exifPolicy: entry.exifPolicy ?? "keep",
          preview: entry.file.type.startsWith("image/") ? URL.createObjectURL(entry.file) : null,
          status: "pending" as const,
          message: t("pages.upload.resumeAvailable"),
        }));
        return [...current, ...restored];
      });
      setResumeLoaded(true);
    }).catch((error: unknown) => {
      setResumeLoaded(true);
      onError(error instanceof Error ? error.message : String(error));
    });
  }, [onError, t]);

  const resumeSignature = items.map((item) => `${item.id}:${item.status}:${item.resumeUploadId ?? ""}:${item.title}:${item.artist}:${item.sourceId}:${item.tags.join("|")}:${item.rotation}:${item.cropLeft}:${item.cropTop}:${item.cropRight}:${item.cropBottom}:${item.flipHorizontal}:${item.flipVertical}:${item.exifPolicy}`).join(";");

  useEffect(() => {
    if (!resumeLoaded) return;
    const resumable = items.filter((item) => item.status !== "done");
    void Promise.all(resumable.map((item) => uploadResumeStore.put({
      id: item.id, file: item.file, title: item.title, artist: item.artist, sourceId: item.sourceId, tags: item.tags, uploadId: item.resumeUploadId, rotation: item.rotation, cropLeft: item.cropLeft, cropTop: item.cropTop, cropRight: item.cropRight, cropBottom: item.cropBottom, flipHorizontal: item.flipHorizontal, flipVertical: item.flipVertical, exifPolicy: item.exifPolicy,
    }))).catch(() => onError(t("pages.upload.resumeStorageFailed")));
    const keep = new Set(resumable.map((item) => item.id));
    void uploadResumeStore.list().then((saved) => Promise.all(saved.filter((entry) => !keep.has(entry.id)).map((entry) => uploadResumeStore.remove(entry.id)))).catch(() => undefined);
  // Persist only queue mutations, not per-chunk progress updates.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeLoaded, resumeSignature, onError, t]);

  useEffect(() => {
    return () => {
      for (const item of itemsRef.current) {
        if (item.preview) URL.revokeObjectURL(item.preview);
      }
    };
  }, []);

  const stats = useMemo(() => {
    const total = items.length;
    const pending = items.filter((item) => item.status === "pending").length;
    const done = items.filter((item) => item.status === "done").length;
    const errored = items.filter((item) => item.status === "error").length;
    const bytes = items.reduce((sum, item) => sum + item.file.size, 0);
    return { total, pending, done, errored, bytes };
  }, [items]);

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const incoming = Array.from(files);
      if (incoming.length === 0) return;
      setItems((prev) => {
        const seen = new Set(prev.map((item) => uploadDedupKey(item.file)));
        const next: UploadItem[] = [...prev];
        let added = 0;
        for (const file of incoming) {
          const dedupKey = uploadDedupKey(file);
          if (seen.has(dedupKey)) continue;
          seen.add(dedupKey);
          next.push({
            id: makeUploadId(file),
            file,
            preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
            title: defaultUploadTitle(file),
            artist: "",
            sourceId: "",
            tags: [],
            rotation: 0,
            cropLeft: 0,
            cropTop: 0,
            cropRight: 0,
            cropBottom: 0,
            flipHorizontal: false,
            flipVertical: false,
            exifPolicy: "keep",
            status: "pending",
          });
          added++;
        }
        if (added > 0) onSuccess(t("pages.upload.uploadedCount", { count: added }));
        return next;
      });
    },
    [onSuccess, t]
  );

  const updateItem = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const setChunkSizeMiB = useCallback((value: number) => {
    const next = Math.min(32, Math.max(1, Math.round(value)));
    setChunkSizeMiBState(next);
    localStorage.setItem("nya.upload.chunk-size-mib", String(next));
  }, []);

  const removeItem = useCallback((id: string) => {
    setItems((prev) => {
      const target = prev.find((item) => item.id === id);
      if (target?.preview) URL.revokeObjectURL(target.preview);
      return prev.filter((item) => item.id !== id);
    });
  }, []);

  const clearAll = useCallback((scope: "all" | "done" | "error" = "all") => {
    setItems((prev) => {
      const keep: UploadItem[] = [];
      for (const item of prev) {
        const drop =
          scope === "all" ? true : scope === "done" ? item.status === "done" : item.status === "error";
        if (drop) {
          if (item.preview) URL.revokeObjectURL(item.preview);
        } else {
          keep.push(item);
        }
      }
      return keep;
    });
  }, []);

  const loadStorageStrategies = useCallback(async () => {
    try {
      const response = await NyaApi.storageStrategies();
      const items = response.items.length > 0
        ? response.items
        : [{ name: response.default_strategy || "local", type: "local", is_default: true, is_remote: false }];
      setStorageStrategies(items);
      setStorageStrategy((current) => (
        items.some((item) => item.name === current)
          ? current
          : response.default_strategy || items[0]?.name || "local"
      ));
      return response;
    } catch (err) {
      setStorageStrategies([LOCAL_STORAGE_STRATEGY]);
      setStorageStrategy("local");
      if (!(err instanceof ApiError && err.status === 404)) {
        onError(err instanceof ApiError ? err.message : String(err));
      }
      return null;
    }
  }, [onError]);

  const uploadAll = useCallback(async () => {
    const queue = items.filter((item) => item.status === "pending" || item.status === "error");
    if (queue.length === 0) {
      onError(t("pages.upload.noPendingFiles"));
      return;
    }

    setSubmitting(true);
    let tagAliases: Record<string, string[]> = {};
    try {
      tagAliases = parseTagAliases(tagAliasesText);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
      return;
    }

    const tagAliasesPayload = Object.keys(tagAliases).length > 0 ? JSON.stringify(tagAliases) : "";
    let okCount = 0;
    let failCount = 0;

    for (const item of queue) {
      updateItem(item.id, { status: "uploading", message: undefined });
      const form = new FormData();
      form.set("file", item.file, item.file.name);
      form.set("last_modified_ms", String(item.file.lastModified));
      form.set("rotation", String(item.rotation));
      form.set("crop_left", String(item.cropLeft));
      form.set("crop_top", String(item.cropTop));
      form.set("crop_right", String(item.cropRight));
      form.set("crop_bottom", String(item.cropBottom));
      form.set("flip_horizontal", String(item.flipHorizontal));
      form.set("flip_vertical", String(item.flipVertical));
      form.set("exif_policy", item.exifPolicy);
      form.set("title", item.title);
      const effectiveArtist = (item.artist || defaultArtist).trim();
      const effectiveTags = item.tags.length > 0 ? item.tags : defaultTags;
      updateItem(item.id, { artist: effectiveArtist, tags: effectiveTags });
      if (effectiveArtist) form.set("artist_name", effectiveArtist);
      if (item.sourceId) form.set("source_id", item.sourceId);
      if (tagAliasesPayload) form.set("tag_aliases", tagAliasesPayload);
      form.set("generate_cache", generateCache ? "true" : "false");
      form.set("storage_strategy", storageStrategy);

      try {
        if (item.file.size > CHUNK_THRESHOLD) {
          await uploadResumeStore.put({ id: item.id, file: item.file, title: item.title, artist: effectiveArtist, sourceId: item.sourceId, tags: effectiveTags, uploadId: item.resumeUploadId, rotation: item.rotation, cropLeft: item.cropLeft, cropTop: item.cropTop, cropRight: item.cropRight, cropBottom: item.cropBottom, flipHorizontal: item.flipHorizontal, flipVertical: item.flipVertical, exifPolicy: item.exifPolicy });
        }
        const asset = await uploadWithChunks(item.file, form, item.resumeUploadId, chunkSizeMiB * 1024 * 1024, (uploadId) => updateItem(item.id, { resumeUploadId: uploadId }), (progress) => updateItem(item.id, { progress }));
        if (effectiveTags.length > 0) {
          try {
            await NyaApi.updateAssetTags(asset.asset_key, effectiveTags);
          } catch {
            // Non-fatal: asset uploaded but tags failed.
          }
        }
        updateItem(item.id, {
          status: "done",
          resumeUploadId: undefined,
          assetKey: asset.asset_key,
          message: asset.duplicate_of ? t("pages.upload.duplicateOf", { assetKey: asset.duplicate_of }) : t("pages.upload.success"),
        });
        okCount++;
      } catch (err) {
        const message = err instanceof ApiError ? err.message : String(err);
        updateItem(item.id, { status: "error", message });
        failCount++;
      }
    }

    setSubmitting(false);
    if (okCount > 0 && failCount === 0) {
      onSuccess(t("pages.upload.summaryAllDone", { count: okCount }));
    } else if (okCount > 0) {
      onSuccess(t("pages.upload.summaryPartial", { ok: okCount, failed: failCount }));
    } else {
      onError(t("pages.upload.allFailed", { count: failCount }));
    }
  }, [chunkSizeMiB, defaultArtist, defaultTags, generateCache, items, onError, onSuccess, storageStrategy, tagAliasesText, t, updateItem]);

  return {
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
  };
}

const CHUNK_THRESHOLD = 16 * 1024 * 1024;
const CHUNK_CONCURRENCY = 3;

type ChunkProgress = (progress: number) => void;

async function uploadWithChunks(
  file: File,
  form: FormData,
  resumeUploadId: string | undefined,
  chunkSize: number,
  onUploadId: (uploadId: string) => void,
  onProgress?: ChunkProgress,
) {
  if (file.size <= CHUNK_THRESHOLD) {
    onProgress?.(50);
    const result = await NyaApi.uploadAsset(form);
    onProgress?.(100);
    return result;
  }
  const bytes = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const sha256 = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
  let chunkSizeForSession = chunkSize;
  let totalChunks = Math.ceil(file.size / chunkSizeForSession);
  let uploadId = resumeUploadId;
  let received: number[] = [];
  if (uploadId) {
    try {
      const status = await NyaApi.chunkUploadStatus(uploadId);
      chunkSizeForSession = status.chunk_size;
      totalChunks = Math.ceil(file.size / chunkSizeForSession);
      if (status.total_chunks !== totalChunks) throw new Error("Upload session does not match the selected file");
      received = status.received;
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
      uploadId = undefined;
    }
  }
  if (!uploadId) {
    const session = await NyaApi.initChunkUpload({ filename: file.name, total_size: file.size, total_chunks: totalChunks, chunk_size: chunkSizeForSession, sha256, content_type: file.type || "application/octet-stream" });
    uploadId = session.upload_id;
    onUploadId(uploadId);
  }
  const completedIndices = new Set(received.filter((index) => Number.isInteger(index) && index >= 0 && index < totalChunks));
  let completed = completedIndices.size;
  const nextIndex = { value: 0 };
  async function worker() {
    while (nextIndex.value < totalChunks) {
      const index = nextIndex.value;
      nextIndex.value += 1;
      if (completedIndices.has(index)) continue;
      await NyaApi.uploadChunk(uploadId!, index, file.slice(index * chunkSizeForSession, Math.min(file.size, (index + 1) * chunkSizeForSession)));
      completed++;
      onProgress?.(Math.round((completed / totalChunks) * 90));
    }
  }
  onProgress?.(Math.round((completed / totalChunks) * 90));
  await Promise.all(Array.from({ length: Math.min(CHUNK_CONCURRENCY, totalChunks) }, () => worker()));
  const complete = new FormData();
  for (const key of ["title", "source_id", "artist_name", "tag_aliases", "storage_strategy", "original_url", "last_modified_ms", "rotation", "crop_left", "crop_top", "crop_right", "crop_bottom", "flip_horizontal", "flip_vertical", "exif_policy"]) {
    const value = form.get(key);
    if (typeof value === "string" && value) complete.set(key, value);
  }
  complete.set("generate_cache", form.get("generate_cache") === "true" ? "true" : "false");
  const result = await NyaApi.completeChunkUpload(uploadId!, complete);
  onProgress?.(100);
  return result;
}

function makeUploadId(file: File): string {
  return `${file.name}__${file.size}__${file.lastModified}__${Math.random()
    .toString(36)
    .slice(2, 7)}`;
}

function uploadDedupKey(file: File): string {
  return `${file.name}__${file.size}__${file.lastModified}`;
}

function defaultUploadTitle(file: File): string {
  const stem = file.name.replace(/\.[^.]+$/, "");
  return stem.trim();
}

function parseTagAliases(value: string): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const rawLine of value.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    let canonical = "";
    let aliases = "";
    if (line.includes("->")) {
      const [left, right] = line.split("->", 2);
      aliases = left;
      canonical = right;
    } else if (line.includes("=")) {
      const [left, right] = line.split("=", 2);
      canonical = left;
      aliases = right;
    } else {
      throw new Error(`Alias format error: ${line}`);
    }

    const tag = canonical.trim().toLowerCase().replace(/\s+/g, "_");
    const names = aliases
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!tag || names.length === 0) {
      throw new Error(`Alias format error: ${line}`);
    }
    result[tag] = Array.from(new Set([...(result[tag] ?? []), ...names]));
  }
  return result;
}
