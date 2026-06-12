"use client";

import { Network, RefreshCw, Save, Search, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LimitGrid, NumberField, ToggleField } from "@/components/admin/admin-fields";
import { AccessLogRow } from "@/components/admin/admin-operation-rows";
import { bytesToMiB, formatDate, limitValue } from "@/components/admin/admin-format";
import type { AccessLogItem, Role, SecurityLimitOverride, SecuritySettings, UserSummary } from "@/lib/types";

const MIB = 1024 * 1024;
const ROLES: Role[] = ["viewer", "editor", "admin", "developer"];

type AdminSecurityPanelProps = {
  busy: string | null;
  securityDraft: SecuritySettings | null;
  users: UserSummary[];
  accessLogs: AccessLogItem[];
  accessLogFilter: string;
  onAccessLogFilterChange: (value: string) => void;
  roleLimitTarget: Role;
  onRoleLimitTargetChange: (value: Role) => void;
  userLimitTarget: string;
  onUserLimitTargetChange: (value: string) => void;
  onRefreshSecurity: () => unknown;
  onSaveSecurity: () => unknown;
  onRefreshAccessLogs: () => unknown;
  onPatchSecurity: (patch: Partial<SecuritySettings>) => void;
  onPatchRoleLimit: (role: string, patch: SecurityLimitOverride) => void;
  onPatchUserLimit: (username: string, patch: SecurityLimitOverride) => void;
};

export function AdminSecurityPanel({
  busy,
  securityDraft,
  users,
  accessLogs,
  accessLogFilter,
  onAccessLogFilterChange,
  roleLimitTarget,
  onRoleLimitTargetChange,
  userLimitTarget,
  onUserLimitTargetChange,
  onRefreshSecurity,
  onSaveSecurity,
  onRefreshAccessLogs,
  onPatchSecurity,
  onPatchRoleLimit,
  onPatchUserLimit,
}: AdminSecurityPanelProps) {
  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Shield className="h-4 w-4" /> 安全与访问控制
          </h2>
          {securityDraft && (
            <p className="mt-1 text-xs text-muted-foreground">
              最近更新：{formatDate(securityDraft.updated_at)} · {securityDraft.updated_by_username || "系统默认"}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={busy === "security-refresh"} onClick={onRefreshSecurity}>
            <RefreshCw className="h-4 w-4" /> 刷新
          </Button>
          <Button size="sm" disabled={!securityDraft || busy === "security-save"} onClick={onSaveSecurity}>
            <Save className="h-4 w-4" /> 保存
          </Button>
        </div>
      </div>

      {securityDraft && (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <ToggleField label="启用安全策略" checked={securityDraft.enabled} onChange={(value) => onPatchSecurity({ enabled: value })} />
            <ToggleField label="记录访问日志" checked={securityDraft.access_log_enabled} onChange={(value) => onPatchSecurity({ access_log_enabled: value })} />
            <NumberField label="日志保留条数" value={securityDraft.access_log_retention} onChange={(value) => onPatchSecurity({ access_log_retention: value })} />
            <NumberField label="上传上限" value={bytesToMiB(securityDraft.max_upload_bytes)} suffix="MiB" onChange={(value) => onPatchSecurity({ max_upload_bytes: value * MIB })} />
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <NumberField label="全局并发" value={securityDraft.max_global_concurrency} onChange={(value) => onPatchSecurity({ max_global_concurrency: value })} />
            <NumberField label="单 IP 并发" value={securityDraft.max_ip_concurrency} onChange={(value) => onPatchSecurity({ max_ip_concurrency: value })} />
            <NumberField label="单 IP 请求/分钟" value={securityDraft.ip_requests_per_minute} onChange={(value) => onPatchSecurity({ ip_requests_per_minute: value })} />
            <NumberField label="单 IP 流量/分钟" value={bytesToMiB(securityDraft.ip_bytes_per_minute)} suffix="MiB" onChange={(value) => onPatchSecurity({ ip_bytes_per_minute: value * MIB })} />
          </div>

          <LimitGrid
            title="默认用户限额"
            concurrency={securityDraft.max_user_concurrency}
            requests={securityDraft.user_requests_per_minute}
            bytesMiB={bytesToMiB(securityDraft.user_bytes_per_minute)}
            onConcurrency={(value) => onPatchSecurity({ max_user_concurrency: value })}
            onRequests={(value) => onPatchSecurity({ user_requests_per_minute: value })}
            onBytesMiB={(value) => onPatchSecurity({ user_bytes_per_minute: value * MIB })}
          />

          <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
            <label className="space-y-1.5">
              <span className="text-xs text-muted-foreground">角色组覆盖</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
                value={roleLimitTarget}
                onChange={(e) => onRoleLimitTargetChange(e.target.value as Role)}
              >
                {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </label>
            <LimitGrid
              title="0 表示继承默认用户限额"
              concurrency={limitValue(securityDraft.role_limits, roleLimitTarget, "max_user_concurrency")}
              requests={limitValue(securityDraft.role_limits, roleLimitTarget, "user_requests_per_minute")}
              bytesMiB={bytesToMiB(limitValue(securityDraft.role_limits, roleLimitTarget, "user_bytes_per_minute"))}
              onConcurrency={(value) => onPatchRoleLimit(roleLimitTarget, { max_user_concurrency: value })}
              onRequests={(value) => onPatchRoleLimit(roleLimitTarget, { user_requests_per_minute: value })}
              onBytesMiB={(value) => onPatchRoleLimit(roleLimitTarget, { user_bytes_per_minute: value * MIB })}
            />
          </div>

          <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
            <label className="space-y-1.5">
              <span className="text-xs text-muted-foreground">用户覆盖</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
                value={userLimitTarget}
                onChange={(e) => onUserLimitTargetChange(e.target.value)}
              >
                {users.map((user) => <option key={user.id} value={user.username}>{user.username} ({user.role})</option>)}
              </select>
            </label>
            <LimitGrid
              title="优先级高于角色组覆盖，0 表示继承"
              concurrency={limitValue(securityDraft.user_limits, userLimitTarget, "max_user_concurrency")}
              requests={limitValue(securityDraft.user_limits, userLimitTarget, "user_requests_per_minute")}
              bytesMiB={bytesToMiB(limitValue(securityDraft.user_limits, userLimitTarget, "user_bytes_per_minute"))}
              onConcurrency={(value) => onPatchUserLimit(userLimitTarget, { max_user_concurrency: value })}
              onRequests={(value) => onPatchUserLimit(userLimitTarget, { user_requests_per_minute: value })}
              onBytesMiB={(value) => onPatchUserLimit(userLimitTarget, { user_bytes_per_minute: value * MIB })}
            />
          </div>
        </>
      )}

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <Network className="h-3.5 w-3.5" /> 访问日志
          </h3>
          <div className="flex min-w-0 flex-1 justify-end gap-2 sm:max-w-md">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={accessLogFilter}
                onChange={(e) => onAccessLogFilterChange(e.target.value)}
                placeholder="过滤 IP / 用户 / 路径 / 拒绝原因"
                className="pl-8"
              />
            </div>
            <Button variant="outline" size="sm" onClick={onRefreshAccessLogs}>
              <RefreshCw className="h-4 w-4" /> 查询
            </Button>
          </div>
        </div>
        <div className="max-h-96 overflow-auto rounded-lg border border-border">
          {accessLogs.map((log) => <AccessLogRow key={log.id} log={log} />)}
          {accessLogs.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">暂无访问日志</div>}
        </div>
      </div>
    </section>
  );
}
