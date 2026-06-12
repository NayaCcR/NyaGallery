"use client";

import type { Dispatch, ReactNode, SetStateAction } from "react";
import { AlertTriangle, KeyRound, Save, Server, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberField, ToggleField } from "@/components/admin/admin-fields";
import type { BackendConfig, DeveloperConfigResponse, DeveloperConsoleResponse, UserSummary } from "@/lib/types";

type AdminDeveloperPanelProps = {
  busy: string | null;
  configResponse: DeveloperConfigResponse | null;
  configDraft: BackendConfig | null;
  onConfigDraftChange: Dispatch<SetStateAction<BackendConfig | null>>;
  onRefreshConfig: () => unknown;
  onSaveConfig: () => unknown;
  consoleStatus: DeveloperConsoleResponse | null;
  onRefreshConsole: () => unknown;
  users: UserSummary[];
  passwordDraft: { username: string; password: string };
  onPasswordDraftChange: Dispatch<SetStateAction<{ username: string; password: string }>>;
  onResetPassword: () => unknown;
};

export function AdminDeveloperPanel({
  busy,
  configResponse,
  configDraft,
  onConfigDraftChange,
  onRefreshConfig,
  onSaveConfig,
  consoleStatus,
  onRefreshConsole,
  users,
  passwordDraft,
  onPasswordDraftChange,
  onResetPassword,
}: AdminDeveloperPanelProps) {
  function patch(section: keyof BackendConfig, values: Record<string, unknown>) {
    onConfigDraftChange((current) => (
      current
        ? ({ ...current, [section]: { ...current[section], ...values } } as BackendConfig)
        : current
    ));
  }

  return (
    <>
      <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <Settings2 className="h-4 w-4" /> 后端配置
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {configResponse
                ? `${configResponse.path}${configResponse.exists ? "" : " · 将新建"}`
                : "读取 nyagallery.toml 后可编辑。"}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={busy === "developer-config-refresh"} onClick={onRefreshConfig}>
              刷新
            </Button>
            <Button size="sm" disabled={!configDraft || busy === "developer-config-save"} onClick={onSaveConfig}>
              <Save className="h-4 w-4" /> 保存配置
            </Button>
          </div>
        </div>

        {configDraft && (
          <div className="space-y-5">
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
              保存会重写 TOML 文件；大多数设置需要重启后端后才会完整生效。Pixiv token/cookie 留空会保留文件中的旧值。
            </div>

            <ConfigGroup title="Core">
              <TextField label="storage" value={configDraft.core.storage} onChange={(value) => patch("core", { storage: value })} />
              <TextField label="database_url" value={configDraft.core.database_url} onChange={(value) => patch("core", { database_url: value })} />
              <TextField label="tag_catalog_path" value={configDraft.core.tag_catalog_path} onChange={(value) => patch("core", { tag_catalog_path: value })} />
            </ConfigGroup>

            <ConfigGroup title="Server">
              <TextField label="host" value={configDraft.server.host} onChange={(value) => patch("server", { host: value })} />
              <NumberField label="port" value={configDraft.server.port} onChange={(value) => patch("server", { port: value })} />
              <ToggleField label="access_log" checked={configDraft.server.access_log} onChange={(value) => patch("server", { access_log: value })} />
              <ToggleField label="secure_cookies" checked={configDraft.server.secure_cookies} onChange={(value) => patch("server", { secure_cookies: value })} />
            </ConfigGroup>

            <ConfigGroup title="Site">
              <TextField label="project_homepage" value={configDraft.site.project_homepage} onChange={(value) => patch("site", { project_homepage: value })} />
              <TextField label="repository" value={configDraft.site.repository} onChange={(value) => patch("site", { repository: value })} />
              <TextField label="icp_beian" value={configDraft.site.icp_beian} onChange={(value) => patch("site", { icp_beian: value })} />
            </ConfigGroup>

            <ConfigGroup title="Pixiv">
              <TextField type="password" label="refresh_token" value={configDraft.pixiv.refresh_token} onChange={(value) => patch("pixiv", { refresh_token: value })} />
              <TextField type="password" label="cookie" value={configDraft.pixiv.cookie} onChange={(value) => patch("pixiv", { cookie: value })} />
              <DecimalField label="default_request_delay_seconds" value={configDraft.pixiv.default_request_delay_seconds} onChange={(value) => patch("pixiv", { default_request_delay_seconds: value })} />
              <NumberField label="max_concurrency" value={configDraft.pixiv.max_concurrency} onChange={(value) => patch("pixiv", { max_concurrency: value })} />
            </ConfigGroup>

            <ConfigGroup title="Redis">
              <TextField label="url" value={configDraft.redis.url} onChange={(value) => patch("redis", { url: value })} />
              <TextField label="key_prefix" value={configDraft.redis.key_prefix} onChange={(value) => patch("redis", { key_prefix: value })} />
              <ToggleField label="security_limiter" checked={configDraft.redis.security_limiter} onChange={(value) => patch("redis", { security_limiter: value })} />
            </ConfigGroup>

            <ConfigGroup title="Developer">
              <ToggleField label="config_editor_enabled" checked={configDraft.developer.config_editor_enabled} onChange={(value) => patch("developer", { config_editor_enabled: value })} />
              <ToggleField label="console_enabled" checked={configDraft.developer.console_enabled} onChange={(value) => patch("developer", { console_enabled: value })} />
            </ConfigGroup>
          </div>
        )}
      </section>

      <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <Server className="h-4 w-4" /> 开发者操作台
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              预留多后端节点列表；当前只接入本地后端的白名单维护动作。
            </p>
          </div>
          <Button variant="outline" size="sm" disabled={busy === "developer-console-refresh"} onClick={onRefreshConsole}>
            刷新
          </Button>
        </div>

        {consoleStatus && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span>{consoleStatus.enabled ? consoleStatus.warning : "开发者操作台未启用；请在配置中打开 console_enabled 并重启后端。"}</span>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {consoleStatus.nodes.map((node) => (
                <div key={node.id} className="space-y-1 rounded-md border border-border p-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{node.label}</span>
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">{node.status}</span>
                  </div>
                  <div className="break-all text-muted-foreground">storage: {node.storage}</div>
                  <div className="break-all text-muted-foreground">database: {node.database_url}</div>
                  <div className="break-all text-muted-foreground">config: {node.config_path}</div>
                  <div className="text-muted-foreground">redis: {node.redis ? "enabled" : "disabled"}</div>
                </div>
              ))}
            </div>

            <div className="space-y-3 rounded-md border border-border p-3">
              <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
                <KeyRound className="h-4 w-4" /> 重置任意用户密码
              </h3>
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
                <div className="space-y-1.5">
                  <Label>用户</Label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
                    value={passwordDraft.username}
                    onChange={(event) => onPasswordDraftChange((draft) => ({ ...draft, username: event.target.value }))}
                  >
                    <option value="">选择用户</option>
                    {users.map((user) => (
                      <option key={user.id} value={user.username}>
                        {user.username} ({user.role})
                      </option>
                    ))}
                  </select>
                </div>
                <TextField
                  type="password"
                  label="新密码"
                  value={passwordDraft.password}
                  onChange={(value) => onPasswordDraftChange((draft) => ({ ...draft, password: value }))}
                />
                <Button
                  variant="destructive"
                  disabled={!consoleStatus.enabled || !passwordDraft.username || !passwordDraft.password || busy === "developer-reset-password"}
                  onClick={onResetPassword}
                >
                  重置
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>
    </>
  );
}

function ConfigGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3 rounded-md border border-border p-3">
      <h3 className="text-xs font-medium uppercase text-muted-foreground">{title}</h3>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{children}</div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function DecimalField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input
        type="number"
        min={0}
        step={0.1}
        value={String(value)}
        onChange={(event) => {
          const parsed = Number(event.target.value);
          onChange(Number.isFinite(parsed) ? Math.max(0, parsed) : 0);
        }}
      />
    </div>
  );
}
