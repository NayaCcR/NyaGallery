import type {
  AccessLogResponse,
  AssetSiblingResponse,
  ApiTokenListResponse,
  Asset,
  BackendConfig,
  DeveloperConfigResponse,
  DeveloperConsoleResponse,
  IssueTokenResponse,
  LoginResponse,
  MeResponse,
  PixivConfigResponse,
  PixivCookieListResponse,
  PixivCookieSummary,
  PixivOAuthExchangeResponse,
  PixivOAuthVisibleSession,
  PixivOAuthStartResponse,
  PixivSyncOptions,
  PixivSyncResponse,
  PixivTokenListResponse,
  PixivTokenSummary,
  SearchOrder,
  RebuildResult,
  SearchResponse,
  SearchSort,
  SecuritySettings,
  SiteConfigResponse,
  StorageStrategiesResponse,
  TagCatalogResponse,
  TagSuggestResponse,
  TagSuggestion,
  TagSummaryResponse,
  TranscodeJobResponse,
  TranscodeJob,
  UploadHistoryResponse,
  UploadLogResponse,
  UserListResponse,
  UserSummary,
} from "./types";

const TOKEN_KEY = "nya.token";
const CSRF_COOKIE = "nya_csrf";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function readCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const escaped = CSRF_COOKIE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | object | null;
  token?: string | null;
  json?: boolean;
};

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = options.token === undefined ? readToken() : options.token;
  if (token) headers.set("authorization", `Bearer ${token}`);
  const method = (options.method || "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  if (unsafe && !headers.has("x-csrf-token")) {
    const csrf = readCsrfToken();
    if (csrf) headers.set("x-csrf-token", csrf);
  }

  let body: BodyInit | undefined;
  if (options.body == null) {
    body = undefined;
  } else if (
    options.json !== false &&
    typeof options.body === "object" &&
    !(options.body instanceof FormData) &&
    !(options.body instanceof Blob) &&
    !(options.body instanceof URLSearchParams) &&
    !(options.body instanceof ArrayBuffer)
  ) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(options.body);
  } else {
    body = options.body as BodyInit;
  }

  const res = await fetch(path, { ...options, headers, body, credentials: options.credentials ?? "same-origin" });

  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = await res.json();
    } catch {
      try {
        detail = await res.text();
      } catch {
        /* ignore */
      }
    }
    const message =
      (detail && typeof detail === "object" && "detail" in detail && typeof (detail as { detail: unknown }).detail === "string"
        ? (detail as { detail: string }).detail
        : null) || `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, message, detail);
  }

  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export const NyaApi = {
  health: () => api<{ ok: boolean; storage: string }>("/health"),

  siteConfig: () => api<SiteConfigResponse>("/api/site/config", { token: null }),

  storageStrategies: () => api<StorageStrategiesResponse>("/api/storage/strategies"),

  me: () => api<MeResponse>("/api/me"),

  login: (username: string, password: string, remember = true) =>
    api<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: { username, password, remember },
      token: null,
    }),

  logout: () =>
    api<{ ok: boolean }>("/api/auth/logout", {
      method: "POST",
      body: {},
      token: null,
    }),

  changePassword: (oldPassword: string, newPassword: string) =>
    api<{ ok: boolean; username: string }>("/api/auth/password", {
      method: "POST",
      body: { old_password: oldPassword, new_password: newPassword },
    }),

  search: (params: { q?: string; limit?: number; offset?: number; sort?: SearchSort; order?: SearchOrder }) => {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    search.set("limit", String(params.limit ?? 50));
    search.set("offset", String(params.offset ?? 0));
    if (params.sort) search.set("sort", params.sort);
    if (params.order) search.set("order", params.order);
    return api<SearchResponse>(`/api/search?${search.toString()}`);
  },

  asset: (assetKey: string) => api<Asset>(`/api/assets/${encodeURIComponent(assetKey)}`),

  assetSiblings: (assetKey: string) =>
    api<AssetSiblingResponse>(`/api/assets/${encodeURIComponent(assetKey)}/siblings`),

  tagSuggest: (q: string, limit = 20) => {
    const search = new URLSearchParams({ q, limit: String(limit) });
    return api<TagSuggestResponse>(`/api/tags/suggest?${search.toString()}`);
  },

  tagCatalog: () => api<TagCatalogResponse>("/api/tags/catalog"),

  tagSummary: () => api<TagSummaryResponse>("/api/tags/summary"),

  exportTagSummary: () =>
    api<{ path: string; total: number }>("/api/tags/summary/export", {
      method: "POST",
      body: {},
    }),

  updateTagAliases: (tagName: string, aliases: string[]) =>
    api<TagSuggestion>(`/api/tags/${encodeURIComponent(tagName)}/aliases`, {
      method: "PUT",
      body: { aliases },
    }),

  updateTagLabels: (tagName: string, labels: Record<string, string>) =>
    api<TagSuggestion>(`/api/tags/${encodeURIComponent(tagName)}/labels`, {
      method: "PUT",
      body: { labels },
    }),

  updateAssetTags: (assetKey: string, canonical_tags: string[]) =>
    api<Asset>(`/api/assets/${encodeURIComponent(assetKey)}/tags`, {
      method: "POST",
      body: { canonical_tags },
    }),

  deleteAsset: (assetKey: string) =>
    api<Asset>(`/api/assets/${encodeURIComponent(assetKey)}`, { method: "DELETE" }),

  cleanupAsset: (assetKey: string) =>
    api<{ asset_key: string; status: string; deleted_files: unknown }>(
      `/api/assets/${encodeURIComponent(assetKey)}/cleanup`,
      { method: "DELETE" }
    ),

  uploadAsset: (form: FormData) =>
    api<Asset>("/api/upload", { method: "POST", body: form, json: false }),

  rebuild: (generate_cache = false) =>
    api<{ assets: number; tags: number; duplicates: number; media: unknown[] }>(
      "/api/rebuild",
      { method: "POST", body: { generate_cache } }
    ),

  generateMedia: (asset_key?: string) =>
    api<{ items: unknown[] }>("/api/media/generate", {
      method: "POST",
      body: { asset_key: asset_key ?? null },
    }),

  uploadHistory: (limit = 50, offset = 0) =>
    api<UploadHistoryResponse>(`/api/uploads/history?limit=${limit}&offset=${offset}`),

  uploadLogs: (limit = 50, offset = 0) =>
    api<UploadLogResponse>(`/api/uploads/logs?limit=${limit}&offset=${offset}`),

  transcodeJobs: (limit = 50, offset = 0) =>
    api<TranscodeJobResponse>(`/api/transcode/jobs?limit=${limit}&offset=${offset}`),

  startTranscode: (assetKey: string) =>
    api<{ job: TranscodeJob | null; status: string }>(
      `/api/transcode/assets/${encodeURIComponent(assetKey)}/start`,
      { method: "POST" }
    ),
  cancelAllTranscode: () =>
    api<{ cancelled: number }>("/api/transcode/cancel-all", { method: "POST" }),

  securitySettings: () => api<SecuritySettings>("/api/security/settings"),

  updateSecuritySettings: (settings: Partial<SecuritySettings>) =>
    api<SecuritySettings>("/api/security/settings", {
      method: "PUT",
      body: settings,
    }),

  accessLogs: (limit = 80, offset = 0, q = "") => {
    const search = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (q.trim()) search.set("q", q.trim());
    return api<AccessLogResponse>(`/api/security/access-logs?${search.toString()}`);
  },

  developerConfig: () => api<DeveloperConfigResponse>("/api/developer/config"),

  updateDeveloperConfig: (config: BackendConfig) =>
    api<DeveloperConfigResponse>("/api/developer/config", {
      method: "PUT",
      body: { config },
    }),

  developerConsole: () => api<DeveloperConsoleResponse>("/api/developer/console"),

  developerResetPassword: (username: string, newPassword: string) =>
    api<UserSummary>("/api/developer/console/reset-password", {
      method: "POST",
      body: { username, new_password: newPassword },
    }),

  pixivConfig: () => api<PixivConfigResponse>("/api/sync/pixiv/config"),

  pixivLogs: (limit = 50, offset = 0) =>
    api<UploadLogResponse>(`/api/sync/pixiv/logs?limit=${limit}&offset=${offset}`),

  pixivOAuthStart: () =>
    api<PixivOAuthStartResponse>("/api/sync/pixiv/oauth/start", {
      method: "POST",
      body: {},
    }),

  pixivOAuthExchange: (payload: { code?: string; callback_url?: string; code_verifier: string; state?: string }) =>
    api<PixivOAuthExchangeResponse>("/api/sync/pixiv/oauth/exchange", {
      method: "POST",
      body: payload,
    }),

  pixivOAuthBrowserLogin: (payload: { username: string; password: string }) =>
    api<PixivOAuthExchangeResponse>("/api/sync/pixiv/oauth/browser-login", {
      method: "POST",
      body: payload,
    }),

  pixivOAuthVisibleStart: (payload: { username?: string; password?: string; timeout_seconds?: number } = {}) =>
    api<PixivOAuthVisibleSession>("/api/sync/pixiv/oauth/visible/start", {
      method: "POST",
      body: payload,
    }),

  pixivOAuthVisibleStatus: (sessionId: string) =>
    api<PixivOAuthVisibleSession>(`/api/sync/pixiv/oauth/visible/${encodeURIComponent(sessionId)}`),

  syncPixivPid: (pid: string, options: PixivSyncOptions = {}) =>
    api<PixivSyncResponse>(
      `/api/sync/pixiv/${encodeURIComponent(pid)}`,
      { method: "POST", body: options }
    ),

  syncPixivUser: (uid: string, options: PixivSyncOptions = {}) =>
    api<PixivSyncResponse>(
      `/api/sync/pixiv/user/${encodeURIComponent(uid)}`,
      { method: "POST", body: options }
    ),

  syncPixivBookmarks: (uid: string, options: PixivSyncOptions = {}) =>
    api<PixivSyncResponse>(
      `/api/sync/pixiv/bookmarks/${encodeURIComponent(uid)}`,
      { method: "POST", body: options }
    ),

  userPixivTokens: (username: string) =>
    api<PixivTokenListResponse>(`/api/users/${encodeURIComponent(username)}/pixiv-tokens`),

  savePixivToken: (
    username: string,
    payload: { refresh_token: string; label?: string; pixiv_user?: Record<string, unknown> | null }
  ) =>
    api<PixivTokenSummary>(
      `/api/users/${encodeURIComponent(username)}/pixiv-token`,
      { method: "POST", body: payload }
    ),

  updatePixivToken: (tokenId: number, label: string) =>
    api<PixivTokenSummary>(
      `/api/pixiv-tokens/${encodeURIComponent(String(tokenId))}`,
      { method: "PATCH", body: { label } }
    ),

  revokePixivToken: (tokenId: number) =>
    api<PixivTokenSummary>(
      `/api/pixiv-tokens/${encodeURIComponent(String(tokenId))}`,
      { method: "DELETE" }
    ),

  userPixivCookies: (username: string) =>
    api<PixivCookieListResponse>(`/api/users/${encodeURIComponent(username)}/pixiv-cookies`),

  savePixivCookie: (
    username: string,
    payload: { cookie: string; label?: string; pixiv_user?: Record<string, unknown> | null }
  ) =>
    api<PixivCookieSummary>(
      `/api/users/${encodeURIComponent(username)}/pixiv-cookie`,
      { method: "POST", body: payload }
    ),

  updatePixivCookie: (cookieId: number, label: string) =>
    api<PixivCookieSummary>(
      `/api/pixiv-cookies/${encodeURIComponent(String(cookieId))}`,
      { method: "PATCH", body: { label } }
    ),

  revokePixivCookie: (cookieId: number) =>
    api<PixivCookieSummary>(
      `/api/pixiv-cookies/${encodeURIComponent(String(cookieId))}`,
      { method: "DELETE" }
    ),

  createUser: (username: string, password: string, role: string) =>
    api<UserSummary>("/api/users", {
      method: "POST",
      body: { username, password, role },
    }),

  users: () => api<UserListResponse>("/api/users"),

  resetUserPassword: (username: string, newPassword: string) =>
    api<UserSummary>(`/api/users/${encodeURIComponent(username)}/password`, {
      method: "POST",
      body: { new_password: newPassword },
    }),

  issueToken: (username: string, label = "") =>
    api<IssueTokenResponse>(
      `/api/users/${encodeURIComponent(username)}/token`,
      { method: "POST", body: { label } }
    ),

  userTokens: (username: string) =>
    api<ApiTokenListResponse>(`/api/users/${encodeURIComponent(username)}/tokens`),

  revokeToken: (tokenId: number) =>
    api<{ id: number; is_active: boolean; revoked_at: string | null }>(
      `/api/tokens/${encodeURIComponent(String(tokenId))}`,
      { method: "DELETE" }
    ),
};

export async function downloadOriginalAsset(asset: Asset): Promise<void> {
  const token = readToken();
  if (!token && readCsrfToken()) {
    const res = await fetch(fileUrl.original(asset.asset_key), { credentials: "same-origin" });
    await saveOriginalDownload(asset, res);
    return;
  }
  if (!token) {
    throw new ApiError(401, "Sign in required to download originals");
  }

  const res = await fetch(fileUrl.original(asset.asset_key), {
    headers: {
      authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const detail = await res.json();
      if (detail && typeof detail === "object" && "detail" in detail) {
        const value = (detail as { detail: unknown }).detail;
        if (typeof value === "string") message = value;
      }
    } catch {
      /* keep HTTP status */
    }
    throw new ApiError(res.status, message);
  }

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromDisposition(res.headers.get("content-disposition"))
    || filenameWithOriginalSuffix(asset.original_filename, asset.original_path)
    || filenameFromPath(asset.original_path)
    || `${asset.asset_key}.bin`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

async function saveOriginalDownload(asset: Asset, res: Response): Promise<void> {
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const detail = await res.json();
      if (detail && typeof detail === "object" && "detail" in detail) {
        const value = (detail as { detail: unknown }).detail;
        if (typeof value === "string") message = value;
      }
    } catch {
      /* keep HTTP status */
    }
    throw new ApiError(res.status, message);
  }

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromDisposition(res.headers.get("content-disposition"))
    || filenameWithOriginalSuffix(asset.original_filename, asset.original_path)
    || filenameFromPath(asset.original_path)
    || `${asset.asset_key}.bin`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function filenameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1]);
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] ?? null;
}

function filenameFromPath(path: string): string | null {
  const name = path.split(/[\\/]/).filter(Boolean).pop();
  return name || null;
}

function filenameWithOriginalSuffix(name: string, path: string): string | null {
  if (!name) return null;
  const suffix = filenameFromPath(path)?.match(/(\.[^.]+)$/)?.[1] ?? "";
  return suffix && !name.toLowerCase().endsWith(suffix.toLowerCase()) ? `${name}${suffix}` : name;
}

// File URLs (no JSON, used as <img src>).
export const fileUrl = {
  preview: (assetKey: string) => `/api/assets/${encodeURIComponent(assetKey)}/preview`,
  thumb: (assetKey: string) => `/api/assets/${encodeURIComponent(assetKey)}/thumb`,
  original: (assetKey: string) => `/api/assets/${encodeURIComponent(assetKey)}/original`,
  randomPreview: (q?: string) => {
    const search = new URLSearchParams();
    if (q) search.set("q", q);
    const qs = search.toString();
    return qs ? `/api/img/random?${qs}` : "/api/img/random";
  },
  randomByTag: (tag: string) => `/api/img/${encodeURIComponent(tag)}`,
};
