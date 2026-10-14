import type { TimelineAsset } from "./types";

export type TimelineGranularity = "day" | "month" | "year";

export function groupTimelineAssets(items: TimelineAsset[], granularity: TimelineGranularity): Array<[string, TimelineAsset[]]> {
  const groups = new Map<string, TimelineAsset[]>();
  for (const item of items) {
    const date = item.timeline_time ? timelineUtcGroupKey(item.timeline_time, granularity) : "unknown";
    groups.set(date, [...(groups.get(date) ?? []), item]);
  }
  return [...groups.entries()];
}

export function timelineUtcGroupKey(value: string, granularity: TimelineGranularity): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "unknown";
  const year = date.getUTCFullYear().toString().padStart(4, "0");
  if (granularity === "year") return year;
  const month = (date.getUTCMonth() + 1).toString().padStart(2, "0");
  return granularity === "month" ? `${year}-${month}` : `${year}-${month}-${date.getUTCDate().toString().padStart(2, "0")}`;
}

export function isValidTimelineDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

export function exclusiveUtcNextDay(value: string): string | null {
  if (!isValidTimelineDate(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString();
}
