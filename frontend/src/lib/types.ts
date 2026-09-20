// Mirror of the FastAPI response shapes we consume.
// See nyagallery/db.py::asset_to_dict and nyagallery/tags.py.

export type Role = "guest" | "viewer" | "editor" | "admin" | "developer";

export interface SiteConfigResponse {
  project_homepage: string;
  repository: string;
  icp_beian: string | null;
  app_name?: string | null;
  logo_url?: string | null;
  layout?: string | null;
}

export interface BackendConfig {
  core: {
    storage: string;
    database_url: string;
    tag_catalog_path: string;
    name_media_by_post_id: boolean;
  };
  server: {
    host: string;
    port: number;
    access_log: boolean;
    secure_cookies: boolean;
  };
  site: {
    project_homepage: string;
    repository: string;
    icp_beian: string;
    app_name: string;
    logo_url: string;
    layout: string;
  };
  media: {
    max_frame_pixels: number;
    max_image_pixels: number;
    max_animation_frames: number;
    max_zip_uncompressed_bytes: number;
    max_zip_frame_bytes: number;
    max_video_bytes: number;
    generation_timeout_seconds: number;
    task_timeout_seconds: number;
    max_concurrency: number;
    upload_read_chunk_bytes: number;
    preview_max_edge: number;
    thumb_max_edge: number;
    avif_quality: number;
    webp_quality: number;
  };
  pixiv: {
    refresh_token: string;
    cookie: string;
    default_request_delay_seconds: number;
    max_concurrency: number;
  };
  network: {
    default_proxy: string;
    proxies: NetworkProxyConfig[];
    sources: NetworkSourceConfig[];
  };
  redis: {
    url: string;
    key_prefix: string;
    security_limiter: boolean;
  };
  security: {
    secret_key: string;
    secret_encryption_enabled?: boolean;
  };
  original_storage: {
    default_strategy: string;
    strategies: StorageStrategyConfig[];
  };
  developer: {
    config_editor_enabled: boolean;
    console_enabled: boolean;
  };
}

export interface NetworkProxyConfig {
  name: string;
  url: string;
  url_configured?: boolean;
  auth_enabled: boolean;
  username: string;
  password: string;
  password_configured?: boolean;
}

export interface NetworkSourceConfig {
  source: string;
  proxy: string;
}

export interface StorageStrategyConfig {
  name: string;
  type: string;
  prefix: string;
  endpoint: string;
  bucket: string;
  region: string;
  username: string;
  password: string;
  token: string;
  access_key_id: string;
  access_key_secret: string;
  drive_id: string;
  root_path: string;
  timeout_seconds: number;
}

export interface StorageStrategySummary {
  name: string;
  type: string;
  is_default: boolean;
  is_remote: boolean;
}

export interface StorageStrategiesResponse {
  default_strategy: string;
  items: StorageStrategySummary[];
}

export interface DeveloperConfigResponse {
  path: string;
  exists: boolean;
  config: BackendConfig;
  secret_fields: string[];
  restart_required: boolean;
  message: string;
}

export interface DeveloperConsoleNode {
  id: string;
  label: string;
  status: string;
  storage: string;
  database_url: string;
  redis: boolean;
  config_path: string;
}

export interface DeveloperConsoleResponse {
  enabled: boolean;
  warning: string;
  nodes: DeveloperConsoleNode[];
  actions: string[];
}

export interface Asset {
  id: string;
  asset_key: string;
  source: string;
  source_id: string;
  page_index: number | null;
  title: string;
  description: string;
  artist: string;
  artist_id: string;
  original_url: string;
  original_filename: string;
  original_path: string;
  file_size?: number | null;
  preview_url: string;
  preview_file_size?: number | null;
  thumb_url: string;
  thumb_file_size?: number | null;
  tags: string[];
  tag_details: TagSuggestion[];
  pixiv_tags: string[];
  pixiv_tag_details: PixivTagDetail[];
  canonical_tags: string[];
  width: number | null;
  height: number | null;
  mime_type: string | null;
  crawl_time: string;
  artwork_date: string | null;
  pixiv_upload_date: string | null;
  source_type: string | null;
  age_rating: string | null;
  is_ai_generated: boolean | null;
  is_animated: boolean | null;
  extra: Record<string, unknown>;
  uploader_user_id: number | null;
  uploader_username: string | null;
  deletion_status: string | null;
  deleted_at: string | null;
  deleted_by_user_id: number | null;
  deleted_by_username: string | null;
  source_file_sha256: string;
  duplicate_of: string | null;
}

export interface AssetApiExamplesResponse {
  asset_key: string;
  formats: Record<string, Record<string, string>>;
}

export interface PixivTagDetail {
  name: string;
  translated_name: string | null;
  source_tag?: string | null;
}

export interface PixivConfigResponse {
  has_env_refresh_token: boolean;
  token_source: "environment" | "request" | string;
  supports_user_sync: boolean;
  supports_generate_cache: boolean;
  supports_browser_oauth_login?: boolean;
  supports_cookie_session_exchange?: boolean;
  storage_strategies: StorageStrategySummary[];
  default_storage_strategy: string;
  secret_encryption_enabled?: boolean;
  proxy_enabled?: boolean;
  auth_modes: PixivAuthMode[];
  default_request_delay_seconds: number;
  max_concurrency: number;
  oauth_note?: string;
  browser_oauth_note?: string;
  manual_oauth_note?: string;
  rate_limit_note: string;
}

export type PixivAuthMode = "public" | "oauth_local" | "oauth" | "oauth_manual" | "refresh_token" | "cookie" | "local_import" | string;

export interface PixivOAuthStartResponse {
  authorization_url: string;
  code_verifier: string;
  code_challenge: string;
  state: string;
  callback_url: string;
}

export interface PixivOAuthExchangeResponse {
  refresh_token: string;
  expires_in: number | null;
  user: Record<string, unknown> | null;
}

export interface PixivOAuthVisibleSession {
  id: string;
  status: "running" | "success" | "error" | string;
  message: string | null;
  created_at: number;
  updated_at: number;
  expires_at: number;
  refresh_token: string | null;
  expires_in: number | null;
  user: Record<string, unknown> | null;
  error: string | null;
}

export interface PixivSyncOptions {
  auth_mode?: PixivAuthMode;
  refresh_token?: string;
  pixiv_token_id?: number | null;
  cookie?: string;
  pixiv_cookie_id?: number | null;
  storage_strategy?: string | null;
  public_first?: boolean;
  rebuild_db?: boolean;
  generate_cache?: boolean;
  limit?: number | null;
  request_delay_seconds?: number;
  max_retries?: number;
  retry_base_seconds?: number;
  retry_max_seconds?: number;
  concurrency?: number;
  dry_run?: boolean;
  restrict?: string;
}

export interface PixivSyncResponse {
  status?: string;
  sync_job_id?: string;
  message?: string;
  sync: unknown[];
  media: unknown[];
  jobs: TranscodeJob[];
  rebuild: RebuildResult | null;
  preview?: unknown[];
}

export type SearchSort =
  | "asset_key"
  | "artwork_date"
  | "pixiv_upload_date"
  | "uploaded_at"
  | "original_filename"
  | "title"
  | "artist"
  | "source"
  | "source_id";

export type SearchOrder = "asc" | "desc";

export interface SearchResponse {
  items: Asset[];
  limit: number;
  offset: number;
  sort: SearchSort;
  order: SearchOrder;
}

export interface AssetSiblingResponse {
  items: Asset[];
  current_asset_key: string;
  source: string;
  source_id: string;
  count: number;
}

export interface PostAttachment {
  position: number;
  asset_key: string | null;
  source_type: string | null;
  remote_url: string;
  thumbnail_url: string;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  description: string;
  is_sensitive: boolean;
  asset_available: boolean;
  preview_url: string | null;
  thumb_url: string | null;
}

export interface Post {
  post_key: string;
  source: string;
  source_id: string;
  author_id: string;
  author_name: string;
  author_handle: string;
  author_avatar_url: string;
  content: string;
  content_warning: string;
  posted_at: string | null;
  crawl_time: string;
  source_url: string;
  language: string | null;
  visibility: string;
  age_rating: string | null;
  tags: string[];
  canonical_tags: string[];
  metrics: Record<string, number>;
  extra: Record<string, unknown>;
  reply_to_url: string;
  repost_of_url: string;
  quote_of_url: string;
  attachment_count: number;
  attachments: PostAttachment[];
}

export interface MisskeyConfigResponse {
  host: string;
  token_configured: boolean;
  default_request_delay_seconds: number;
  page_size: number;
  download_concurrency: number;
  proxy_configured: boolean;
  storage_strategies: StorageStrategySummary[];
  default_storage_strategy: string;
  note: string;
}

export interface MisskeyTokenSummary {
  id: number;
  user_id: number;
  token_prefix: string;
  token_suffix: string;
  label: string;
  host: string;
  misskey_user_id: string | null;
  misskey_username: string | null;
  misskey_name: string | null;
  created_by_user_id: number | null;
  created_by_username: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  revoked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
}

export interface MisskeyTokenListResponse {
  items: MisskeyTokenSummary[];
}

export interface MisskeySyncOptions {
  token?: string;
  misskey_token_id?: number;
  host?: string;
  storage_strategy?: string;
  limit?: number;
  page_size?: number;
  max_pages?: number;
  include_replies?: boolean;
  backfill?: boolean;
  download_media?: boolean;
  download_concurrency?: number;
  request_delay_seconds?: number;
  rebuild_db?: boolean;
  generate_cache?: boolean;
  dry_run?: boolean;
}

export interface MisskeyNotePreview {
  note_id: string;
  created_at: string;
  text: string;
  cw: string;
  file_count: number;
  url: string;
  tags: string[];
}

export interface MisskeyUserPreview {
  user_id: string;
  username: string;
  name: string;
  handle: string;
  avatar_url: string;
  notes_count: number | null;
}

export interface MisskeySyncResponse {
  status?: string;
  sync_job_id?: string;
  message?: string;
  sync: unknown[];
  posts: unknown[];
  media: unknown[];
  jobs: unknown[];
  rebuild: unknown;
  preview?: MisskeyNotePreview[];
  user?: MisskeyUserPreview;
}

export interface XConfigResponse {
  host: string;
  session_configured: boolean;
  default_request_delay_seconds: number;
  page_size: number;
  download_concurrency: number;
  proxy_configured: boolean;
  storage_strategies: StorageStrategySummary[];
  default_storage_strategy: string;
  note: string;
}

export interface XTokenSummary {
  id: number;
  user_id: number;
  token_prefix: string;
  token_suffix: string;
  has_ct0: boolean;
  label: string;
  host: string;
  x_user_id: string | null;
  x_screen_name: string | null;
  x_name: string | null;
  created_by_user_id: number | null;
  created_by_username: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  revoked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
}

export interface XTokenListResponse {
  items: XTokenSummary[];
}

export interface XSyncOptions {
  auth_token?: string;
  ct0?: string;
  x_token_id?: number;
  targets?: string[];
  storage_strategy?: string;
  limit?: number;
  page_size?: number;
  max_pages?: number;
  include_replies?: boolean;
  media_only?: boolean;
  backfill?: boolean;
  download_media?: boolean;
  download_concurrency?: number;
  request_delay_seconds?: number;
  rebuild_db?: boolean;
  generate_cache?: boolean;
  dry_run?: boolean;
}

export interface XTweetPreview {
  tweet_id: string;
  created_at: string;
  text: string;
  screen_name: string;
  media_count: number;
  media_types: string[];
  url: string;
  tags: string[];
  metrics: Record<string, number>;
}

export interface XUserPreview {
  user_id: string;
  screen_name: string;
  name: string;
  handle: string;
  avatar_url: string;
  tweets_count: number | null;
  media_count: number | null;
  is_protected: boolean;
}

export interface XPostFailure {
  target: string;
  error: string;
  tweet_id: string | null;
}

export interface XSyncResponse {
  status?: string;
  sync_job_id?: string;
  message?: string;
  sync: unknown[];
  posts: unknown[];
  media: unknown[];
  jobs: unknown[];
  rebuild: unknown;
  failures: XPostFailure[];
  preview?: XTweetPreview[];
  user?: XUserPreview;
}

export interface FanboxConfigResponse {
  session_configured: boolean;
  default_request_delay_seconds: number;
  page_size: number;
  download_concurrency: number;
  download_files: boolean;
  proxy_configured: boolean;
  supports_pixiv_cookie_login: boolean;
  storage_strategies: StorageStrategySummary[];
  default_storage_strategy: string;
  note: string;
}

export interface FanboxSessionSummary {
  id: number;
  user_id: number;
  session_prefix: string;
  session_suffix: string;
  label: string;
  source: string;
  fanbox_user_id: string | null;
  fanbox_creator_id: string | null;
  fanbox_name: string | null;
  created_by_user_id: number | null;
  created_by_username: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  revoked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
}

export interface FanboxSessionListResponse {
  items: FanboxSessionSummary[];
}

export interface FanboxLoginResponse {
  session_id: string;
  saved: FanboxSessionSummary | null;
  identity: Record<string, unknown>;
}

export interface FanboxSyncOptions {
  session_id?: string;
  fanbox_session_id?: number;
  targets?: string[];
  storage_strategy?: string;
  limit?: number;
  page_size?: number;
  max_pages?: number;
  backfill?: boolean;
  download_media?: boolean;
  download_files?: boolean;
  download_concurrency?: number;
  request_delay_seconds?: number;
  rebuild_db?: boolean;
  generate_cache?: boolean;
  dry_run?: boolean;
}

export interface FanboxPostPreview {
  post_id: string;
  title: string;
  post_type: string;
  published_at: string;
  fee_required: number;
  locked: boolean;
  file_count: number;
  tags: string[];
  url: string;
}

export interface FanboxCreatorPreview {
  creator_id: string;
  user_id: string;
  name: string;
  icon_url: string;
  has_adult_content: boolean;
  is_supported: boolean;
}

export interface FanboxSyncResponse {
  status?: string;
  sync_job_id?: string;
  message?: string;
  sync: unknown[];
  posts: unknown[];
  media: unknown[];
  jobs: unknown[];
  rebuild: unknown;
  failures: { target: string; error: string; post_id: string | null }[];
  preview?: FanboxPostPreview[];
  creator?: FanboxCreatorPreview;
}

export type PostSort = "posted_at" | "added";

export interface PostSourceCount {
  source: string;
  count: number;
}

export interface PostListResponse {
  items: Post[];
  limit: number;
  offset: number;
  order: SearchOrder;
  source: string;
  q: string;
  total: number;
  has_more: boolean;
  sources: PostSourceCount[];
}

export interface TagSuggestion {
  name: string;
  category: string;
  aliases: string[];
  labels: Record<string, string>;
  implications: string[];
  suggestions: string[];
  description?: string;
}

export interface TagCategorySummary {
  name: string;
  color: string;
  order: number;
  is_default: boolean;
}

export interface TagCatalogResponse {
  categories: TagCategorySummary[];
  tags: TagSuggestion[];
}

export interface TagSummaryItem extends TagSuggestion {
  count: number;
  source: "catalog" | "catalog+observed" | "observed";
}

export interface TagSummaryResponse {
  categories: TagCategorySummary[];
  items: TagSummaryItem[];
  total: number;
}

export interface TagSuggestResponse {
  items: TagSuggestion[];
}

export interface RebuildResult {
  assets: number;
  tags: number;
  duplicates: number;
  media: unknown[];
}

export interface TranscodeJob {
  id: number;
  job_id: string;
  asset_key: string;
  uploader_user_id: number | null;
  uploader_username: string | null;
  status: "queued" | "running" | "success" | "error" | string;
  stage: string;
  message: string;
  progress: number;
  frames_done: number | null;
  frames_total: number | null;
  frames_per_second: number | null;
  file_size: number | null;
  kind: string | null;
  source: string;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  stage_started_at: string | null;
  finished_at: string | null;
  updated_at: string | null;
}

export interface UploadHistoryItem {
  asset_key: string;
  title: string;
  original_filename: string;
  original_path: string;
  file_size: number | null;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  is_animated: boolean | null;
  uploaded_at: string | null;
  uploader_user_id: number | null;
  uploader_username: string | null;
  duplicate_of: string | null;
  preview_path: string | null;
  thumb_path: string | null;
  has_preview_cache: boolean;
  has_thumb_cache: boolean;
  cache_status: "ready" | "partial" | "missing" | string;
  is_hidden: boolean;
  latest_transcode_job: TranscodeJob | null;
}

export interface UploadLogItem {
  id: number;
  asset_key: string | null;
  uploader_user_id: number | null;
  uploader_username: string | null;
  original_filename: string;
  file_size: number | null;
  mime_type: string | null;
  event: string;
  status: string;
  message: string;
  extra: Record<string, unknown>;
  has_preview_cache?: boolean;
  has_thumb_cache?: boolean;
  cache_status?: "ready" | "partial" | "missing" | string;
  is_hidden?: boolean;
  created_at: string | null;
}

export interface UploadHistoryResponse {
  items: UploadHistoryItem[];
  limit: number;
  offset: number;
}

export interface UploadLogResponse {
  items: UploadLogItem[];
  limit: number;
  offset: number;
}

export interface TranscodeJobResponse {
  items: TranscodeJob[];
  limit: number;
  offset: number;
}

export interface SecuritySettings {
  enabled: boolean;
  access_log_enabled: boolean;
  access_log_retention: number;
  max_global_concurrency: number;
  max_ip_concurrency: number;
  max_user_concurrency: number;
  ip_requests_per_minute: number;
  ip_bytes_per_minute: number;
  user_requests_per_minute: number;
  user_bytes_per_minute: number;
  viewer_requests_per_minute: number;
  max_upload_bytes: number;
  role_limits: Record<string, SecurityLimitOverride>;
  user_limits: Record<string, SecurityLimitOverride>;
  viewer_api_whitelist_enabled: boolean;
  viewer_api_whitelist: string[];
  csrf_origin_check_enabled: boolean;
  trusted_origins: string[];
  trust_proxy_headers: boolean;
  updated_by_username: string | null;
  updated_at: string | null;
}

export interface SecurityLimitOverride {
  max_user_concurrency?: number;
  user_requests_per_minute?: number;
  user_bytes_per_minute?: number;
}

export interface AccessLogItem {
  id: number;
  client_ip: string;
  user_id: number | null;
  username: string | null;
  role: Role | string | null;
  method: string;
  path: string;
  query_string: string;
  status_code: number;
  duration_ms: number;
  request_bytes: number | null;
  response_bytes: number | null;
  user_agent: string;
  referer: string;
  origin: string;
  rejection_reason: string | null;
  error: string | null;
  created_at: string | null;
}

export interface AccessLogResponse {
  items: AccessLogItem[];
  limit: number;
  offset: number;
  q: string;
}

export interface UserSummary {
  id: number;
  username: string;
  role: Role;
}

export interface UserListResponse {
  items: UserSummary[];
}

export interface IssueTokenResponse {
  token: string;
}

export interface MeResponse {
  username: string;
  role: Role;
  user_id: number | null;
  permissions: string[];
  auth_method?: "guest" | "session" | "bearer" | string;
  csrf_token?: string | null;
}

export interface LoginResponse extends MeResponse {}

export interface ApiTokenSummary {
  id: number;
  user_id: number;
  token_prefix: string;
  label: string;
  created_by_user_id: number | null;
  created_by_username: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  revoked_at: string | null;
  created_at: string | null;
  is_active: boolean;
}

export interface ApiTokenListResponse {
  items: ApiTokenSummary[];
}

export interface PixivTokenSummary {
  id: number;
  user_id: number;
  token_prefix: string;
  token_suffix: string;
  label: string;
  pixiv_user_id: string | null;
  pixiv_account: string | null;
  pixiv_name: string | null;
  created_by_user_id: number | null;
  created_by_username: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  revoked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
}

export interface PixivTokenListResponse {
  items: PixivTokenSummary[];
}

export interface PixivCookieSummary {
  id: number;
  user_id: number;
  cookie_prefix: string;
  cookie_suffix: string;
  label: string;
  pixiv_user_id: string | null;
  pixiv_account: string | null;
  pixiv_name: string | null;
  created_by_user_id: number | null;
  created_by_username: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  revoked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
}

export interface PixivCookieListResponse {
  items: PixivCookieSummary[];
}
