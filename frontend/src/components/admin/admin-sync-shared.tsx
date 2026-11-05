"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { ListChecks, RefreshCw, Save, ShieldAlert, Trash2 } from "lucide-react";
import { EmptyLine } from "@/components/admin/admin-fields";
import { formatDate } from "@/components/admin/admin-format";
import { useI18n } from "@/components/providers/locale-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { AdminPollingMode } from "@/hooks/admin/use-admin-operations";
import { SyncLogList, type SyncBulkAction } from "@/components/admin/admin-sync-log-list";
import type { StorageStrategySummary, UploadLogItem } from "@/lib/types";

/**
 * Shared layout for platform sync sections (pixiv / misskey / x / fanbox):
 * sync form on the left, credentials on the right, sync logs full width below.
 */
export function SyncPanelLayout({ main, side, logs }: { main: ReactNode; side: ReactNode; logs: ReactNode }) {
  return (
    <div className="space-y-6">
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        {main}
        <aside className="space-y-6">{side}</aside>
      </div>
      {logs}
    </div>
  );
}

export function SyncCard({
  icon: Icon,
  title,
  description,
  actions,
  className,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Icon className="h-4 w-4" /> {title}
          </h2>
          {description && <div className="mt-1 text-xs leading-5 text-muted-foreground">{description}</div>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** A labelled group inside a sync card, used to separate target / fetch / storage settings. */
export function SyncFieldGroup({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("space-y-3", className)}>
      {title && <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</div>}
      {children}
    </div>
  );
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: {
  value: T;
  options: Array<{ value: T; label: string; disabled?: boolean }>;
  onChange: (value: T) => void;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn("flex flex-wrap gap-1 rounded-lg border border-border bg-muted/40 p-1", className)}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "h-8 min-w-[4.5rem] flex-1 rounded-md px-3 text-xs font-medium transition-colors focus-ring disabled:cursor-not-allowed disabled:opacity-50",
              active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function SyncNumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  allowEmpty = false,
  hint,
  suffix,
}: {
  label: string;
  value: number | "";
  onChange: (value: number | "") => void;
  min?: number;
  max?: number;
  step?: number;
  allowEmpty?: boolean;
  hint?: string;
  suffix?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="relative">
        <Input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value === "" ? "" : String(value)}
          className={cn(suffix && "pr-8")}
          onChange={(event) => {
            const raw = event.target.value;
            if (raw === "" && allowEmpty) {
              onChange("");
              return;
            }
            const parsed = Number(raw);
            if (!Number.isFinite(parsed)) return;
            onChange(Math.min(max ?? Number.MAX_SAFE_INTEGER, Math.max(min ?? 0, parsed)));
          }}
        />
        {suffix && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground">{suffix}</span>
        )}
      </div>
      {hint && <p className="text-[11px] leading-4 text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function StorageStrategySelect({
  label,
  value,
  strategies,
  onChange,
}: {
  label: string;
  value: string;
  strategies: StorageStrategySummary[] | undefined;
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();
  const options = strategies?.length ? strategies : [{ name: value || "local", type: "local", is_default: true, is_remote: false }];
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <select
        className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((strategy) => (
          <option key={strategy.name} value={strategy.name}>
            {strategy.name}
            {strategy.is_default ? ` (${t("common.defaultOption")})` : ""}
            {strategy.type && strategy.type !== strategy.name ? ` · ${strategy.type}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

export function SyncSwitchGroup({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-x-5 gap-y-2.5 rounded-md border border-border bg-muted/35 p-3">{children}</div>;
}

export function SyncNotice({ tone = "warning", children }: { tone?: "warning" | "info"; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border px-3 py-2 text-[11px] leading-5 text-muted-foreground",
        tone === "warning" ? "border-amber-500/40 bg-amber-500/10" : "border-primary/20 bg-primary/5"
      )}
    >
      {tone === "warning" && <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function SyncSubmitButton({
  busy,
  disabled,
  dryRun,
  label,
  dryRunLabel,
  onClick,
}: {
  busy: boolean;
  disabled?: boolean;
  dryRun: boolean;
  label: string;
  dryRunLabel: string;
  onClick: () => unknown;
}) {
  return (
    <Button disabled={busy || disabled} onClick={() => void onClick()} className="w-full" variant={dryRun ? "outline" : "default"}>
      <RefreshCw className={cn("h-4 w-4", busy && "animate-spin")} /> {dryRun ? dryRunLabel : label}
    </Button>
  );
}

/**
 * Full-width log card under the sync form. `ns` is the i18n namespace that owns
 * logsTitle / emptyLogs / pollingActive / pollingIdle / pollingPaused (e.g. "admin.misskey").
 */
export function SyncLogsSection({
  ns,
  logs,
  pollingMode,
  lastUpdatedAt,
  refreshing,
  onRefresh,
  bulkBusy,
  onBulkAction,
  renderRow,
  before,
}: {
  ns: string;
  logs: UploadLogItem[];
  pollingMode: AdminPollingMode;
  lastUpdatedAt: string | null;
  refreshing: boolean;
  onRefresh: () => unknown;
  bulkBusy: boolean;
  onBulkAction: (action: SyncBulkAction, assetKeys: string[]) => unknown;
  renderRow: (log: UploadLogItem) => ReactNode;
  before?: ReactNode;
}) {
  const { t } = useI18n();
  const count = logs.length;
  const pollingKey = pollingMode === "active" ? "pollingActive" : pollingMode === "idle" ? "pollingIdle" : "pollingPaused";
  return (
    <SyncCard
      icon={ListChecks}
      title={`${t(`${ns}.logsTitle`)}${count > 0 ? ` · ${count}` : ""}`}
      description={
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("h-1.5 w-1.5 rounded-full", pollingMode === "active" ? "animate-pulse bg-emerald-500" : pollingMode === "idle" ? "bg-muted-foreground/60" : "bg-amber-500")} />
          {t(`${ns}.${pollingKey}`)}
          {lastUpdatedAt && ` · ${formatDate(lastUpdatedAt)}`}
        </span>
      }
      actions={
        <Button variant="outline" size="sm" disabled={refreshing} onClick={() => void onRefresh()} aria-label={t("admin.ops.refresh")} title={t("admin.ops.refresh")}>
          <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
        </Button>
      }
    >
      {before}
      {count === 0 ? (
        <EmptyLine text={t(`${ns}.emptyLogs`)} />
      ) : (
        <div className="max-h-[640px] overflow-auto pr-1">
          <SyncLogList logs={logs} busy={bulkBusy} onBulkAction={onBulkAction} renderRow={renderRow} />
        </div>
      )}
    </SyncCard>
  );
}

export type SavedCredential = {
  id: number;
  title: string;
  meta?: string;
  isActive: boolean;
  label: string;
  lastUsedAt?: string | null;
};

/** Select + list of saved credentials with inline rename / revoke, shared by misskey / x / fanbox. */
export function SavedCredentialList({
  ns,
  selectLabel,
  noneLabel,
  emptyLabel,
  labelPlaceholder,
  busyPrefix,
  busy,
  items,
  selectedId,
  onSelect,
  labelDrafts,
  onLabelDraftChange,
  onUpdateLabel,
  onRevoke,
}: {
  ns: string;
  selectLabel: string;
  noneLabel: string;
  emptyLabel: string;
  labelPlaceholder: string;
  busyPrefix: { label: string; revoke: string };
  busy: string | null;
  items: SavedCredential[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  labelDrafts: Record<number, string>;
  onLabelDraftChange: (id: number, value: string) => void;
  onUpdateLabel: (id: number) => unknown;
  onRevoke: (id: number) => unknown;
}) {
  const { t } = useI18n();
  const active = items.filter((item) => item.isActive);
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>{selectLabel}</Label>
        <select
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
          value={selectedId ? String(selectedId) : ""}
          onChange={(event) => onSelect(event.target.value ? Number(event.target.value) : null)}
        >
          <option value="">{noneLabel}</option>
          {active.map((item) => (
            <option key={item.id} value={String(item.id)}>
              {item.title}
            </option>
          ))}
        </select>
      </div>
      {items.length === 0 ? (
        <EmptyLine text={emptyLabel} />
      ) : (
        <div className="max-h-72 space-y-2 overflow-auto pr-1">
          {items.map((item) => (
            <div
              key={item.id}
              className={cn(
                "space-y-2 rounded-md border border-border p-3 text-xs transition-colors",
                selectedId === item.id && "border-primary/45 bg-primary/5",
                !item.isActive && "opacity-60"
              )}
            >
              <button
                type="button"
                disabled={!item.isActive}
                onClick={() => onSelect(selectedId === item.id ? null : item.id)}
                className="flex w-full items-center justify-between gap-2 text-left disabled:cursor-default"
              >
                <span className="min-w-0 truncate font-medium" title={item.title}>{item.title}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {item.isActive ? item.meta : t(`${ns}.revoked`)}
                </span>
              </button>
              <div className="text-[11px] text-muted-foreground">
                {item.lastUsedAt ? t(`${ns}.lastUsed`, { at: formatDate(item.lastUsedAt) }) : t(`${ns}.neverUsed`)}
              </div>
              {item.isActive && (
                <div className="flex gap-2">
                  <Input
                    className="h-8 text-xs"
                    value={labelDrafts[item.id] ?? item.label}
                    placeholder={labelPlaceholder}
                    onChange={(event) => onLabelDraftChange(item.id, event.target.value)}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 px-2"
                    aria-label={t("common.save")}
                    title={t("common.save")}
                    disabled={busy === `${busyPrefix.label}${item.id}`}
                    onClick={() => void onUpdateLabel(item.id)}
                  >
                    <Save className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2 text-destructive hover:text-destructive"
                    aria-label={t("admin.tokens.revoke")}
                    title={t("admin.tokens.revoke")}
                    disabled={busy === `${busyPrefix.revoke}${item.id}`}
                    onClick={() => void onRevoke(item.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}