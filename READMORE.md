# NyaGallery

A self-hosted picture library system for anime illustration collection.

Documentation: [project home](README.md) | [中文首页](docs/README_CN.md) | [中文完整说明](docs/READMORE_CN.md) | [中文快速启动](docs/QUICKSTART_CN.md) | [中文使用手册](docs/USAGE_CN.md) | [实现总结](docs/summary.md) | [frontend details](frontend/README.md).

## Current V1 implementation

This repository currently implements the V1 full-stack foundation:

- Pixiv artwork/user sync through a replaceable client adapter.
- Immutable original file storage under `storage/original`.
- One rebuildable creator-grouped metadata JSON file under `storage/metadata`.
- A Szurubooru-style tag catalog with canonical tags, aliases, implications, suggestions, categories, and query parsing.
- A rebuildable SQLAlchemy database index sourced from metadata JSON plus the tag catalog.
- FastAPI endpoints for search, random images, original/preview files, tag suggestions, uploads, cache generation, Pixiv sync, and admin rebuilds.
- Multi-user roles, HttpOnly cookie sessions, CSRF protection, and bearer API tokens for scripts.
- Rebuildable AVIF previews/thumbs and animated WebP cache for Pixiv ugoira ZIP files.
- A Next.js frontend for masonry browsing, search, upload, asset details, login, and admin workflows.
- Security settings, access logs, operation logs, upload history, and transcode job tracking.

## Storage layout

```text
storage/
├─ original/
├─ preview/
├─ thumbs/
├─ metadata/
└─ tags/
```

Original files are never overwritten. If a sync tries to write the same archive path with different bytes, the storage layer raises an error instead of replacing the file.

## Metadata

Metadata is grouped by creator. A file such as `storage/metadata/pixiv_88888.json` contains an `assets` array:

```json
{
  "schema": "nyagallery.creator_metadata.v1",
  "creator_key": "pixiv_88888",
  "creator": {
    "artist_id": "88888",
    "artist_name": "Artist"
  },
  "assets": [
    {
      "source": "pixiv",
      "source_id": "123456",
      "title": "Example",
      "artist_id": "88888",
      "artist_name": "Artist",
      "original_url": "https://www.pixiv.net/artworks/123456",
      "crawl_time": "2026-06-06T12:00:00Z",
      "file_sha256": "...",
      "original_filename": "123456",
      "original_path": "original/123456.jpg",
      "pixiv_tags": ["raw Pixiv tag"],
      "canonical_tags": []
    }
  ]
}
```

`pixiv_tags` are raw source tags and should not be modified. `canonical_tags` is reserved for user-curated standard tags so the database can be rebuilt from files later. Automatically resolved tags are produced by the tag catalog during database rebuilds, not written back into Pixiv metadata. Pixiv tag details are also indexed as `source_tag:*`: translated names become canonical tag bodies when available, and original names are kept as aliases. The generic `source_tag` category is intended for future source platforms too.
Uploads also record `uploader_user_id` and `uploader_username`. If no artist is provided on upload, metadata is grouped into `user_{id}.json`.

## Tag catalog

Create the default catalog:

```powershell
python -m pip install -e .
nyagallery --storage storage init-tags
```

The catalog supports:

- Canonical tags such as `character:misaka_mikoto`.
- Aliases such as `御坂美琴`, `Misaka Mikoto`, or `misaka_mikoto`.
- Backend-owned display labels such as `labels: {"zh-CN": "御坂美琴", "en-US": "Misaka Mikoto"}`. Frontends choose the current locale from the catalog response instead of keeping separate tag translations.
- Implications such as `character:misaka_mikoto` implying `series:toaru`.
- Suggestions for related tags.
- Automatic aspect tags: `meta:landscape`, `meta:portrait`, `meta:square`, common ratios such as `meta:aspect_16_9` / `meta:aspect_9_16`, `meta:unusual_aspect`, and wallpaper recommendations such as `meta:landscape_wallpaper` / `meta:portrait_wallpaper`.
- Source-site tags such as `source_tag:cat`; raw Pixiv names and translated names are linked through aliases so either form can be searched without duplicating curated `character:` / `series:` tags.
- Hidden tags: `hide` normalizes to `meta:hide`, while `/hide-xxx` normalizes to `meta:hide_xxx`. Hidden-tagged assets are excluded from normal frontend browsing, random images, and public tag lists unless the hidden tag is explicitly queried; the admin tag section can still search and maintain them.
- Queries with required/excluded tags and original filename terms, for example `character:misaka_mikoto -rating:r18` or `filename:2026-04-22`.

## Pixiv sync

Install optional Pixiv support, then use the local browser OAuth helper to obtain a refresh token:

```powershell
python -m pip install -e ".[pixiv,pixiv-login,media]"
nyagallery --storage storage pixiv-login-browser --plain
$env:PIXIV_REFRESH_TOKEN = "your-refresh-token"
nyagallery --storage storage pixiv-sync-pid 123456
nyagallery --storage storage pixiv-sync-user 88888 --limit 50
nyagallery --storage storage pixiv-sync-pid 123456 --generate-cache --rebuild-db
```

If you pass a token directly and it starts with `-`, use the equals form: `--refresh-token=...`.

The admin Pixiv `OAuth` panel can also obtain a refresh token through the backend when `pixiv-login` is installed. Use that only on a trusted self-hosted instance because Pixiv credentials are submitted to the NyaGallery backend for that request.

The sync service can also be used directly with a fake or custom `PixivClient`, which keeps the archival logic testable without network access.

## Configuration File

The backend supports a unified TOML config. Copy `config.example.toml` to `nyagallery.toml`, then run:

```powershell
nyagallery --config nyagallery.toml serve
```

The file covers runtime settings such as `core.storage`, `core.database_url`, `server.host`, `server.port`, `site.project_homepage`, `site.icp_beian`, `pixiv.refresh_token`, optional Redis settings, and `[developer]` switches for the admin config editor and allowlisted developer console. CLI arguments override environment variables, and environment variables override the config file. Leave `site.icp_beian` empty to hide the ICP filing link in the frontend footer.

Users with the `developer` role inherit admin capabilities and can access the admin developer module. Admin users cannot create developer users from the web UI/API; use the CLI or an existing developer account for that trust boundary. The developer console intentionally does not expose arbitrary shell execution; it only enables explicit maintenance actions such as privileged password resets when `developer.console_enabled = true`.

Redis is optional and disabled by default. Install `python -m pip install -e ".[redis]"`, then set `[redis].url`. Turning on `redis.security_limiter` moves request concurrency/rate/traffic limiting from process memory to Redis so multiple API instances share the same limits.

## Database rebuild

SQLite is used by default for local development:

```powershell
nyagallery --storage storage rebuild-db
```

Migrate old per-asset metadata JSON files into creator-grouped JSON files:

```powershell
nyagallery --storage storage migrate-metadata
```

Use PostgreSQL by passing any SQLAlchemy PostgreSQL URL:

```powershell
python -m pip install -e ".[postgres]"
nyagallery --storage storage --database-url "postgresql+psycopg://user:pass@localhost/nyagallery" rebuild-db
```

The database stores searchable indexes, users, and API tokens. Gallery assets still come from `original/` and `metadata/`, so the asset index can be rebuilt at any time.

## Media cache

Install media support:

```powershell
python -m pip install -e ".[media]"
```

Generate cache for all assets:

```powershell
nyagallery --storage storage generate-cache
nyagallery --storage storage rebuild-db --generate-cache
```

Static images produce:

```text
storage/preview/{asset_key}.avif
storage/thumbs/{asset_key}.avif
```

Pixiv ugoira ZIP files produce:

```text
storage/preview/{asset_key}.webp
storage/thumbs/{asset_key}.avif
```

These files are cache only and can be deleted/regenerated.

## Users and API

One-command local setup:

```powershell
nyagallery --storage storage setup
```

This initializes tags, migrates metadata, rebuilds the database, creates the admin user, and issues a bearer token.

Manual admin creation and token issuing:

```powershell
nyagallery --storage storage create-user admin --role admin
nyagallery --storage storage issue-token admin
```

Start the API:

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

Useful endpoints:

- `GET /health`
- `GET /api/site/config`
- `GET /api/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/auth/password`
- `GET /api/search?q=character:misaka_mikoto -rating:r18`
- `GET /api/img/random`
- `GET /api/img/{tag}`
- `GET /api/assets/{asset_key}`
- `GET /api/assets/{asset_key}/siblings`
- `GET /api/assets/{asset_key}/original`
- `GET /api/assets/{asset_key}/preview`
- `GET /api/assets/{asset_key}/thumb`
- `GET /api/tags/suggest?q=御坂`
- `GET /api/tags/catalog`
- `GET /api/tags/summary`
- `POST /api/tags/summary/export`
- `PUT /api/tags/{tag_name}/aliases`
- `PUT /api/tags/{tag_name}/labels`
- `POST /api/upload`
- `POST /api/assets/{asset_key}/tags`
- `POST /api/media/generate`
- `POST /api/rebuild`
- `GET /api/uploads/history`
- `GET /api/uploads/logs`
- `GET /api/transcode/jobs`
- `POST /api/transcode/assets/{asset_key}/start`
- `GET /api/security/settings`
- `PUT /api/security/settings`
- `GET /api/security/access-logs`
- `GET /api/sync/pixiv/config`
- `POST /api/sync/pixiv/oauth/start`
- `POST /api/sync/pixiv/oauth/exchange`
- `POST /api/sync/pixiv/oauth/browser-login`
- `POST /api/sync/pixiv/oauth/visible/start`
- `GET /api/sync/pixiv/oauth/visible/{session_id}`
- `POST /api/sync/pixiv/{pid}`
- `POST /api/sync/pixiv/user/{uid}`
- `POST /api/sync/pixiv/session/exchange`
- `POST /api/users`
- `GET /api/users`
- `POST /api/users/{username}/password`
- `POST /api/users/{username}/token`
- `GET /api/users/{username}/tokens`
- `DELETE /api/tokens/{token_id}`
- `POST /api/users/{username}/pixiv-token`
- `GET /api/users/{username}/pixiv-tokens`
- `POST /api/users/{username}/pixiv-cookie`
- `GET /api/users/{username}/pixiv-cookies`
- `DELETE /api/assets/{asset_key}`
- `DELETE /api/assets/{asset_key}/cleanup`

Read endpoints allow guest access. The web frontend uses cookie sessions and CSRF tokens. Scripts and external clients can use bearer API tokens with the matching role permission.

Delete flow:

- `DELETE /api/assets/{asset_key}` marks an asset as `pending_cleanup`, records `deleted_by_username`, `deleted_by_user_id`, and `deleted_at` in metadata, and hides it from normal search/detail/random responses.
- `DELETE /api/assets/{asset_key}/cleanup` is admin-only and permanently removes the pending asset's original file, generated cache files, database row, and metadata entry.

## Tests

```powershell
python -m pip install -e ".[dev,media]"
python -m pytest
cd frontend
npm run typecheck
```
