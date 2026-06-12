# NyaGallery

文档导航：[中文首页](README_CN.md) | [英文首页](../README.md) | [英文完整说明](../READMORE.md) | [中文快速启动](QUICKSTART_CN.md) | [中文使用手册](USAGE_CN.md) | [实现总结](summary.md) | [前端说明](../frontend/README.md)。

面向二次元插画收藏的自部署图库系统。

## 当前 V1 实现

当前仓库已经实现 V1 全栈基础：

- Pixiv 作品/作者同步，Pixiv 客户端适配器可替换。
- 原始文件不可变归档，保存到 `storage/original`。
- 每个创作者对应一个可重建的 metadata JSON，保存到 `storage/metadata`。
- Szurubooru 风格标签目录，支持标准标签、别名、蕴含、建议、分类和查询解析。
- 基于 `metadata.json` 与标签目录重建的 SQLAlchemy 数据库索引。
- FastAPI 接口：搜索、排序、随机图、原图/预览文件、标签建议、上传、缓存生成、Pixiv 同步、管理员重建。
- 多用户角色、HttpOnly Cookie 会话、CSRF 防护，以及给脚本使用的 Bearer API Token。
- 可重建的 AVIF 预览/缩略图，以及 Pixiv ugoira ZIP 对应的 Animated WebP 缓存。
- Next.js 前端：瀑布流浏览、标签搜索、上传、详情页、登录和管理后台。
- 安全设置、访问日志、操作日志、上传历史和转码任务进度。

## 存储结构

```text
storage/
├─ original/
├─ preview/
├─ thumbs/
├─ metadata/
└─ tags/
```

原始文件永不覆盖。如果同步时试图向同一个归档路径写入不同内容，存储层会直接报错，而不是替换已有文件。

## 元数据

metadata 按创作者分组。例如 `storage/metadata/pixiv_88888.json` 内部包含一个 `assets` 数组：

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

`pixiv_tags` 是来源站点的原始标签，不应修改。`canonical_tags` 保留给用户维护的标准标签，确保数据库未来可以从文件重新导入。自动解析出来的标签会在重建索引时由标签目录计算，不会写回 Pixiv 原始元数据。Pixiv 抓取到的标签细节也会进入 `source_tag:*`：有翻译时优先用翻译名作为规范标签体，原文保留为别名；这套通用 `source_tag` 分类也为后续接入其他来源平台预留。
上传资源会额外记录 `uploader_user_id` 和 `uploader_username`。如果上传时没有填写作者，则会归入 `user_{id}.json`。

## 标签目录

创建默认标签目录：

```powershell
python -m pip install -e .
nyagallery --storage storage init-tags
```

标签目录支持：

- 标准标签，例如 `character:misaka_mikoto`。
- 标签别名，例如 `御坂美琴`、`Misaka Mikoto`、`misaka_mikoto`。
- 后端标签显示名，例如 `labels: {"zh-CN": "御坂美琴", "en-US": "Misaka Mikoto"}`；前端只根据当前语言选择 catalog 返回的显示名，不在前端语言文件里维护标签翻译。
- 标签蕴含，例如 `character:misaka_mikoto` 自动蕴含 `series:toaru`。
- 相关标签建议。
- 自动比例标签：`meta:landscape`、`meta:portrait`、`meta:square`、`meta:aspect_16_9`、`meta:aspect_9_16`、`meta:aspect_1_1`、`meta:unusual_aspect`、`meta:landscape_wallpaper`、`meta:portrait_wallpaper`。
- 来源、日期、类型和安全级别派生标签：`source:pixiv`、`source:upload`、`date:2026_05_20`、`type:ugoira`、`rating:r18`、`meta:ai_generated`。
- 来源站点标签：例如 Pixiv 的 `猫` / `cat` 会统一索引为 `source_tag:cat` 并把 `猫` 作为别名，便于搜索，也避免和人工维护的 `character:`、`series:` 标签混在一起。
- 隐藏标签：`hide` 会规范化为 `meta:hide`，`/hide-xxx` 会规范化为 `meta:hide_xxx`；这类资源默认不进入前台搜索/随机图/标签列表，显式搜索 `hide` 或 `/hide-xxx` 时才会返回，并仍可在管理页标签模块中搜索。
- 必选/排除标签查询，例如 `character:misaka_mikoto -rating:r18`。
- 原始文件名查询，例如 `filename:2026-04-22` 或直接输入文件名片段。

## Pixiv 同步

安装可选 Pixiv、Pixiv 登录助手与媒体依赖。推荐用本机浏览器 OAuth 流程获取 refresh token：

```powershell
python -m pip install -e ".[pixiv,pixiv-login,media]"
nyagallery --storage storage pixiv-login-browser --plain
$env:PIXIV_REFRESH_TOKEN = "your-refresh-token"
nyagallery --storage storage pixiv-sync-pid 123456
nyagallery --storage storage pixiv-sync-user 88888 --limit 50
nyagallery --storage storage pixiv-sync-pid 123456 --generate-cache --rebuild-db
```

如果直接传 `--refresh-token`，且 token 以 `-` 开头，请使用 `--refresh-token=...` 的等号形式。

管理页的 Pixiv `OAuth` 面板也可以在后端已安装 `pixiv-login` 时直接获取 refresh token；这会把 Pixiv 账号密码提交给当前 NyaGallery 后端，仅建议可信管理员在自部署实例上使用。

同步服务也可以直接接入假的或自定义的 `PixivClient`，这样归档逻辑可以在没有网络的情况下测试。

## 配置文件

后端支持统一 TOML 配置。复制 `config.example.toml` 为 `nyagallery.toml` 后即可用：

```powershell
nyagallery --config nyagallery.toml serve
```

配置文件包含 `core.storage`、`core.database_url`、`server.host`、`server.port`、`site.project_homepage`、`site.icp_beian`、`pixiv.refresh_token`、可选 Redis，以及 `[developer]` 中的管理页配置编辑器和白名单开发者操作台开关。命令行参数优先于环境变量，环境变量优先于配置文件；`site.icp_beian` 留空时前端页脚不显示备案号。

`developer` 角色继承 admin 能力，并额外拥有开发者模块入口。admin 不能通过 Web UI/API 创建 developer 用户；这个信任边界只能走本机 CLI 或已有 developer 账号。开发者操作台不会开放任意 shell 执行，只在 `developer.console_enabled = true` 时启用明确的维护动作，例如特权账号密码重置。

Redis 默认关闭。安装 `python -m pip install -e ".[redis]"` 后设置 `[redis].url`，再打开 `redis.security_limiter` 可以把请求并发、频率和流量限制从进程内存切换到 Redis，方便多个 API 实例共享同一套限流状态。

## 数据库重建

本地开发默认使用 SQLite：

```powershell
nyagallery --storage storage rebuild-db
```

把旧的“每个文件一个 JSON”迁移为“每个创作者一个 JSON”：

```powershell
nyagallery --storage storage migrate-metadata
```

也可以传入任意 SQLAlchemy PostgreSQL URL：

```powershell
python -m pip install -e ".[postgres]"
nyagallery --storage storage --database-url "postgresql+psycopg://user:pass@localhost/nyagallery" rebuild-db
```

数据库保存搜索索引、用户和 API Token。图库资产仍然来自 `original/` 与 `metadata/`，因此资产索引可以随时重建。

## 媒体缓存

安装媒体依赖：

```powershell
python -m pip install -e ".[media]"
```

为全部资源生成缓存：

```powershell
nyagallery --storage storage generate-cache
nyagallery --storage storage rebuild-db --generate-cache
```

静态图片会生成：

```text
storage/preview/{asset_key}.avif
storage/thumbs/{asset_key}.avif
```

Pixiv ugoira ZIP 会生成：

```text
storage/preview/{asset_key}.webp
storage/thumbs/{asset_key}.avif
```

这些文件只是展示缓存，可以删除后重新生成。

## 用户与 API

一键初始化：

```powershell
nyagallery --storage storage setup
```

它会初始化标签目录、迁移 metadata、重建数据库、创建管理员并签发 Bearer Token。

手动创建管理员并签发 Token：

```powershell
nyagallery --storage storage create-user admin --role admin
nyagallery --storage storage issue-token admin
```

启动 API：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

常用接口：

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

读取类接口允许访客访问。网页端使用 Cookie 会话和 CSRF Token；脚本和外部客户端可以继续使用具备对应角色权限的 Bearer API Token。

删除流程：

- `DELETE /api/assets/{asset_key}` 会把资源标记为 `pending_cleanup`，在 metadata 中记录 `deleted_by_username`、`deleted_by_user_id` 和 `deleted_at`，并从普通搜索、详情和随机图结果中隐藏。
- `DELETE /api/assets/{asset_key}/cleanup` 仅管理员可用，会彻底删除待清理资源的原图、缓存文件、数据库记录和 metadata 条目。

## 测试

```powershell
python -m pip install -e ".[dev,media]"
python -m pytest
cd frontend
npm run typecheck
```
