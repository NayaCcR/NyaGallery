"use client";

import type { Dispatch, ReactNode, SetStateAction } from "react";
import { AlertTriangle, KeyRound, Plus, Save, Server, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberField, ToggleField } from "@/components/admin/admin-fields";
import { useI18n } from "@/components/providers/locale-provider";
import type { BackendConfig, DeveloperConfigResponse, DeveloperConsoleResponse, UserSummary } from "@/lib/types";

const NETWORK_SOURCE_OPTIONS = [
  { source: "pixiv", label: "Pixiv" },
] as const;

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
  const { t } = useI18n();

  function patch(section: keyof BackendConfig, values: Record<string, unknown>) {
    onConfigDraftChange((current) => (
      current
        ? ({ ...current, [section]: { ...current[section], ...values } } as BackendConfig)
        : current
    ));
  }

  function patchNetwork(values: Partial<BackendConfig["network"]>) {
    onConfigDraftChange((current) => (
      current
        ? (() => {
            const fallback = current.network ?? { default_proxy: "", proxies: [], sources: [] };
            const network = { ...fallback, ...values };
            return {
              ...current,
              network,
            } as BackendConfig;
          })()
        : current
    ));
  }

  function updateProxy(index: number, values: Partial<BackendConfig["network"]["proxies"][number]>) {
    const network = configDraft?.network ?? { default_proxy: "", proxies: [], sources: [] };
    patchNetwork({
      proxies: network.proxies.map((proxy, proxyIndex) => (
        proxyIndex === index ? { ...proxy, ...values } : proxy
      )),
    });
  }

  function addProxy() {
    const network = configDraft?.network ?? { default_proxy: "", proxies: [], sources: [] };
    patchNetwork({
      proxies: [
        ...network.proxies,
        {
          name: nextProxyName(network.proxies.map((proxy) => proxy.name)),
          url: "",
          auth_enabled: false,
          username: "",
          password: "",
        },
      ],
    });
  }

  function setSourceProxy(source: string, proxy: string) {
    const network = configDraft?.network ?? { default_proxy: "", proxies: [], sources: [] };
    const sourceKey = normalizeSourceKey(source);
    const nextSources = network.sources.filter((item) => normalizeSourceKey(item.source) !== sourceKey);
    const proxyRef = proxy.trim();
    if (proxyRef) {
      nextSources.push({ source: sourceKey, proxy: proxyRef });
    }
    patchNetwork({
      sources: nextSources,
    });
  }

  function removeProxy(index: number) {
    const network = configDraft?.network ?? { default_proxy: "", proxies: [], sources: [] };
    patchNetwork({ proxies: network.proxies.filter((_proxy, proxyIndex) => proxyIndex !== index) });
  }

  const networkDraft = configDraft?.network ?? { default_proxy: "", proxies: [], sources: [] };
  const savedNetwork = configResponse?.config.network ?? networkDraft;

  return (
    <>
      <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <Settings2 className="h-4 w-4" /> {t("admin.developer.configTitle")}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {configResponse
                ? `${configResponse.path}${configResponse.exists ? "" : t("admin.maintenance.willCreateSuffix")}`
                : t("admin.developer.configDescription")}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={busy === "developer-config-refresh"} onClick={onRefreshConfig}>
              {t("common.refresh")}
            </Button>
            <Button size="sm" disabled={!configDraft || busy === "developer-config-save"} onClick={onSaveConfig}>
              <Save className="h-4 w-4" /> {t("admin.developer.saveConfig")}
            </Button>
          </div>
        </div>

        {configDraft && (
          <div className="space-y-5">
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
              {t("admin.developer.saveWarning")}
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

            <ConfigGroup title="Network">
              <div className="md:col-span-2 xl:col-span-3">
                <div className="rounded-md border border-border bg-muted/35 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                  {t("admin.developer.networkHint")}
                </div>
              </div>
              <SelectField
                label="default_proxy"
                value={networkDraft.default_proxy}
                options={proxyReferenceOptions(savedNetwork, networkDraft.default_proxy, false)}
                onChange={(value) => patchNetwork({ default_proxy: value })}
              />
              <div className="space-y-2 md:col-span-2 xl:col-span-3">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-medium uppercase text-muted-foreground">{t("admin.developer.proxyProfiles")}</h4>
                  <Button type="button" size="sm" variant="outline" onClick={addProxy}>
                    <Plus className="h-4 w-4" /> {t("admin.developer.addProxyProfile")}
                  </Button>
                </div>
                <div className="space-y-2">
                  {networkDraft.proxies.map((proxy, index) => (
                    <div key={`proxy-${index}`} className="grid gap-2 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)_auto]">
                      <TextField label="name" value={proxy.name} placeholder="local" onChange={(value) => updateProxy(index, { name: value })} />
                      <div className="space-y-2">
                        <TextField label="url" value={proxy.url ?? ""} placeholder="http://127.0.0.1:7890" onChange={(value) => updateProxy(index, { url: value })} />
                        <ToggleField
                          label="proxy_auth"
                          checked={proxy.auth_enabled ?? false}
                          onChange={(value) => updateProxy(index, {
                            auth_enabled: value,
                            ...(value ? {} : { username: "", password: "" }),
                          })}
                        />
                        {proxy.auth_enabled ? (
                          <div className="grid gap-2 sm:grid-cols-2">
                            <TextField label="username" value={proxy.username ?? ""} onChange={(value) => updateProxy(index, { username: value })} />
                            <TextField type="password" label="password" value={proxy.password ?? ""} onChange={(value) => updateProxy(index, { password: value })} />
                            {proxy.password_configured && !proxy.password ? (
                              <div className="sm:col-span-2 rounded-md border border-border bg-muted/35 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                                {t("admin.developer.proxyPasswordConfigured")}
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                      <ProxyRowActions
                        saveLabel={t("admin.developer.saveConfig")}
                        removeLabel={t("common.removeItem", { item: proxy.name || "proxy" })}
                        saveDisabled={!configDraft || busy === "developer-config-save"}
                        onSave={onSaveConfig}
                        onRemove={() => removeProxy(index)}
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div className="space-y-2 md:col-span-2 xl:col-span-3">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-medium uppercase text-muted-foreground">{t("admin.developer.sourceProxyRules")}</h4>
                </div>
                <div className="space-y-2">
                  {NETWORK_SOURCE_OPTIONS.map((source) => {
                    const current = networkDraft.sources.find((item) => normalizeSourceKey(item.source) === source.source)?.proxy ?? "";
                    return (
                      <div key={source.source} className="grid gap-2 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
                        <div className="space-y-1.5">
                          <Label>source</Label>
                          <div className="flex h-9 items-center justify-between gap-2 rounded-md border border-border bg-muted/35 px-3 text-sm">
                            <span>{source.label}</span>
                            <span className="font-mono text-xs text-muted-foreground">{source.source}</span>
                          </div>
                        </div>
                        <SelectField
                          label="proxy"
                          value={current}
                          options={proxyReferenceOptions(savedNetwork, current, true)}
                          onChange={(value) => setSourceProxy(source.source, value)}
                        />
                      </div>
                    );
                  })}
                  {networkDraft.sources
                    .filter((source) => !NETWORK_SOURCE_OPTIONS.some((option) => option.source === normalizeSourceKey(source.source)))
                    .map((source) => (
                      <div key={source.source} className="grid gap-2 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
                        <div className="space-y-1.5">
                          <Label>source</Label>
                          <div className="flex h-9 items-center rounded-md border border-border bg-muted/35 px-3 font-mono text-xs text-muted-foreground">
                            {normalizeSourceKey(source.source)}
                          </div>
                        </div>
                        <SelectField
                          label="proxy"
                          value={source.proxy}
                          options={proxyReferenceOptions(savedNetwork, source.proxy, true)}
                          onChange={(value) => setSourceProxy(source.source, value)}
                        />
                      </div>
                    ))}
                </div>
              </div>
            </ConfigGroup>

            <ConfigGroup title="Redis">
              <TextField label="url" value={configDraft.redis.url} onChange={(value) => patch("redis", { url: value })} />
              <TextField label="key_prefix" value={configDraft.redis.key_prefix} onChange={(value) => patch("redis", { key_prefix: value })} />
              <ToggleField label="security_limiter" checked={configDraft.redis.security_limiter} onChange={(value) => patch("redis", { security_limiter: value })} />
            </ConfigGroup>

            <ConfigGroup title="Security">
              <div className="md:col-span-2 xl:col-span-3">
                <div className="flex items-start gap-2 rounded-md border border-border bg-muted/35 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                  <span>{t("admin.developer.secretHint")}</span>
                </div>
              </div>
              <TextField type="password" label="secret_key" value={configDraft.security?.secret_key ?? ""} onChange={(value) => patch("security", { secret_key: value })} />
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
              <Server className="h-4 w-4" /> {t("admin.developer.consoleTitle")}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("admin.developer.consoleDescription")}
            </p>
          </div>
          <Button variant="outline" size="sm" disabled={busy === "developer-console-refresh"} onClick={onRefreshConsole}>
            {t("common.refresh")}
          </Button>
        </div>

        {consoleStatus && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span>{consoleStatus.enabled ? consoleStatus.warning : t("admin.developer.consoleDisabled")}</span>
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
                <KeyRound className="h-4 w-4" /> {t("admin.developer.resetPasswordTitle")}
              </h3>
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
                <div className="space-y-1.5">
                  <Label>{t("auth.username")}</Label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
                    value={passwordDraft.username}
                    onChange={(event) => onPasswordDraftChange((draft) => ({ ...draft, username: event.target.value }))}
                  >
                    <option value="">{t("admin.developer.selectUser")}</option>
                    {users.map((user) => (
                      <option key={user.id} value={user.username}>
                        {user.username} ({user.role})
                      </option>
                    ))}
                  </select>
                </div>
                <TextField
                  type="password"
                  label={t("admin.accounts.newPassword")}
                  value={passwordDraft.password}
                  onChange={(value) => onPasswordDraftChange((draft) => ({ ...draft, password: value }))}
                />
                <Button
                  variant="destructive"
                  disabled={!consoleStatus.enabled || !passwordDraft.username || !passwordDraft.password || busy === "developer-reset-password"}
                  onClick={onResetPassword}
                >
                  {t("admin.accounts.reset")}
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
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <select
        className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-ring"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={`${option.value}:${option.label}`} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ProxyRowActions({
  saveLabel,
  removeLabel,
  saveDisabled,
  onSave,
  onRemove,
}: {
  saveLabel: string;
  removeLabel: string;
  saveDisabled: boolean;
  onSave: () => unknown;
  onRemove: () => void;
}) {
  return (
    <div className="mt-6 flex gap-2">
      <Button type="button" variant="outline" size="icon" title={saveLabel} aria-label={saveLabel} disabled={saveDisabled} onClick={onSave}>
        <Save className="h-4 w-4" />
      </Button>
      <IconButton label={removeLabel} onClick={onRemove} />
    </div>
  );
}

function IconButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button type="button" variant="outline" size="icon" title={label} aria-label={label} onClick={onClick}>
      <Trash2 className="h-4 w-4" />
    </Button>
  );
}

function nextProxyName(names: string[]) {
  return nextName(names, "proxy");
}

function nextName(names: string[], base: string) {
  const existing = new Set(names.map((name) => name.trim().toLowerCase()).filter(Boolean));
  if (!existing.has(base)) return base;
  let index = 2;
  while (existing.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

function normalizeSourceKey(value: string) {
  return value.trim().toLowerCase().replace(/[-.]/g, "_");
}

function proxyReferenceOptions(
  network: BackendConfig["network"],
  currentValue: string,
  includeDefault: boolean,
) {
  const options: { value: string; label: string }[] = [];
  const seen = new Set<string>();

  function add(value: string, label = value) {
    const key = value.trim().toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    options.push({ value, label });
  }

  if (includeDefault) {
    add("", "default_proxy");
  } else if (!currentValue.trim()) {
    add("", "direct");
  }
  add("direct");
  for (const proxy of network.proxies) {
    const name = proxy.name.trim();
    if (name) add(name);
  }
  const current = currentValue.trim();
  if (current) add(current);
  return options;
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
