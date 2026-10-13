"use client";

import { Input } from "@/components/ui/input";
import { useI18n } from "@/components/providers/locale-provider";

export function LimitGrid({
  title,
  concurrency,
  requests,
  bytesMiB,
  onConcurrency,
  onRequests,
  onBytesMiB,
}: {
  title: string;
  concurrency: number;
  requests: number;
  bytesMiB: number;
  onConcurrency: (value: number) => void;
  onRequests: (value: number) => void;
  onBytesMiB: (value: number) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="grid gap-3 md:grid-cols-3">
        <NumberField label={t("admin.security.concurrency")} value={concurrency} onChange={onConcurrency} />
        <NumberField label={t("admin.security.requestsPerMinute")} value={requests} onChange={onRequests} />
        <NumberField label={t("admin.security.trafficPerMinute")} value={bytesMiB} suffix="MiB" onChange={onBytesMiB} />
      </div>
    </div>
  );
}

export function ToggleField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex h-9 items-center justify-between gap-3 rounded-md border border-border px-3 text-sm">
      <span className="min-w-0 truncate">{label}</span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-primary" />
    </label>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <select
        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
}) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <Input type="number" min={0} value={String(value)} onChange={(e) => onChange(toNonNegativeInt(e.target.value))} />
        {suffix && <span className="w-10 text-xs text-muted-foreground">{suffix}</span>}
      </div>
    </label>
  );
}

export function TextAreaField({
  label,
  value,
  onChange,
  rows,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows: number;
}) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus-ring"
      />
    </label>
  );
}

export function EmptyLine({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">{text}</div>;
}

function toNonNegativeInt(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.round(parsed));
}
