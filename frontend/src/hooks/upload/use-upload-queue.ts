"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { StorageStrategySummary } from "@/lib/types";

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
  message?: string;
  assetKey?: string;
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
  const [dragActive, setDragActive] = useState(false);
  const itemsRef = useRef<UploadItem[]>([]);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

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
      form.set("title", item.title);
      const effectiveArtist = (item.artist || defaultArtist).trim();
      if (effectiveArtist) form.set("artist_name", effectiveArtist);
      if (item.sourceId) form.set("source_id", item.sourceId);
      if (tagAliasesPayload) form.set("tag_aliases", tagAliasesPayload);
      form.set("generate_cache", generateCache ? "true" : "false");
      form.set("storage_strategy", storageStrategy);

      try {
        const asset = await NyaApi.uploadAsset(form);
        const effectiveTags = item.tags.length > 0 ? item.tags : defaultTags;
        if (effectiveTags.length > 0) {
          try {
            await NyaApi.updateAssetTags(asset.asset_key, effectiveTags);
          } catch {
            // Non-fatal: asset uploaded but tags failed.
          }
        }
        updateItem(item.id, {
          status: "done",
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
  }, [defaultArtist, defaultTags, generateCache, items, onError, onSuccess, storageStrategy, tagAliasesText, t, updateItem]);

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
