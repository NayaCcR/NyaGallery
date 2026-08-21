# NyaGallery 当前实现总结

本文档总结当前已实现的主要功能与模块，不替代 README / 使用文档。

文档导航：[中文首页](README_CN.md) | [中文完整说明](READMORE_CN.md) | [快速启动](QUICKSTART_CN.md) | [使用手册](USAGE_CN.md) | [生产部署](PRODUCTION_DEPLOYMENT_CN.md) | [配置解析](CONFIGURATION_CN.md) | [API 参考](API_CN.md) | [开发指南](DEVELOPMENT_CN.md) | [前端说明](../frontend/README.md) | [英文首页](../README.md)。

## 项目定位

NyaGallery 是一个自部署图库系统，面向 Pixiv 同步、个人上传、原图归档、标签搜索、预览缓存、权限管理与 Web 浏览。

当前项目由两部分组成：

- 后端：FastAPI + SQLAlchemy，提供图库 API、鉴权、索引、转码、日志和安全限制。
- 前端：Next.js 14 + TypeScript + Tailwind，提供瀑布流浏览、搜索、上传、详情、管理和登录体验。

## 后端模块

### CLI

入口命令为 `nyagallery`，由 `pyproject.toml` 注册到 `nyagallery.cli:main`。

已实现命令：

- `setup`：初始化 storage、标签目录、数据库、管理员和 API Token。
- `serve`：启动 FastAPI 服务。
- `init-tags`：创建默认标签目录。
- `pixiv-sync-pid`：按 Pixiv PID 同步单个作品。
- `pixiv-sync-user`：按 Pixiv 用户 UID 同步作品。
- `migrate-metadata`：将旧的单资源 metadata JSON 迁移为按创作者/上传者分组的 JSON。
- `rebuild-db`：从 metadata JSON 重建数据库索引。
- `generate-cache`：生成预览图、缩略图、动图 WebP 缓存。
- `create-user`：创建用户。
- `issue-token`：为账号签发 API Token。
- `set-password`：设置或重置账号密码。
- `security-config`：查看或修改部分安全配置。

### Storage 与 Metadata

已实现文件分区：

- `storage/original/`：不可变原始文件归档。
- `storage/preview/`：压缩预览缓存。
- `storage/thumbs/`：缩略图缓存。
- `storage/metadata/`：可重建数据库的 JSON 元数据。
- `storage/tags/`：标签目录与导出结果。

Metadata 已支持：

- 保留原始文件。
- 保存原始路径、上传/来源文件名、sha256、标题、作者、Pixiv 信息、尺寸、日期、分级、AI、动图信息。
- 上传者 `uploader_user_id` / `uploader_username`。
- 删除标记与删除者信息。
- 按创作者或上传者聚合为较大的 JSON 文件。
- 从用户日常 Pixiv 文件命名中解析作品日期、标题、PID、页码等部分信息。

### Pixiv 同步

已实现：

- 通过 Pixiv PID 同步作品。
- 通过 Pixiv 用户 UID 批量同步作品。
- 多图作品按页生成 asset key。
- 保留 Pixiv 原图和元数据。
- 记录 Pixiv 标签、标题、作者、作者 ID、作品日期、上传日期、作品类型、R-18/R-18G、AI 标记。
- 支持 ugoira 信息与帧延迟数据写入 metadata。
- 同步后可重建数据库索引。

### 数据库索引

数据库使用 SQLAlchemy 模型。

主要表：

- `assets`：资源索引。
- `asset_tags`：资源标签索引。
- `users`：账号。
- `user_tokens`：账号绑定的多个 API Token。
- `login_sessions`：Cookie 登录会话与 CSRF Token。
- `transcode_jobs`：转码任务、阶段、进度、帧数、fps、耗时字段。
- `upload_logs`：上传/转码请求/转码结果日志。
- `access_logs`：安全访问日志。
- `security_settings`：安全配置。

数据库可从 metadata JSON 重建。

### 标签系统

已实现 Szurubooru 风格标签目录：

- 标签分类：`artist`、`uploader`、`source`、`character`、`series`、`type`、`clothing`、`rating`、`date`、`meta`、`general`。
- canonical tag。
- aliases。
- implications。
- suggestions。
- description。
- 标签自动补全。
- 标签汇总。
- 标签汇总导出。
- 管理端可编辑标签别名。

自动派生标签：

- 来源：如 `source:pixiv`、`source:upload`。
- 上传者：如 `uploader:admin`，但前端不把 uploader 当 artist 展示。
- 作者：如 `artist:*`。
- 类型：如 `type:illustration`、`type:manga`、`type:ugoira`。
- 分级：`rating:safe`、`rating:r18`、`rating:r18g`，并支持 `r18` / `R-18` 等别名。
- AI：`meta:ai_generated`。
- 动图：`meta:animated`。
- 日期：`date:YYYY`、`date:YYYY_MM`、`date:YYYY_MM_DD`。
- 方向：`meta:landscape`、`meta:portrait`、`meta:square`。
- 常见比例：如 `meta:aspect_16_9`、`meta:aspect_9_16`。
- 异形比例：`meta:unusual_aspect`。
- 壁纸推荐：`meta:landscape_wallpaper`、`meta:portrait_wallpaper`。

动图仅保留比例/方向标签，不参与壁纸推荐标签。

### 搜索与排序

已实现：

- `/api/search` 搜索资源。
- 多标签 AND 搜索。
- `-tag` 排除语法。
- 标签 alias 解析。
- 文件名搜索，支持 `filename:*` 和自由文本命中文件名。
- guest 自动排除敏感分级内容。
- 支持排序：
  - asset key
  - 作品日期
  - Pixiv 上传/修改日期
  - 入库/上传时间
  - 原始文件名
  - 标题
  - 作者
  - 来源
  - 来源 ID

### 上传

已实现：

- Web/API 上传文件。
- 上传时保留原始文件。
- asset key 与下载文件名分离。
- 下载时保留上传时的文件名主体，并补回真实后缀。
- 上传时可填写标题、作者、默认标签、标签别名。
- 上传时自动识别图片尺寸、动图状态、R-18/R-18G 相关标签别名、比例/方向标签。
- 可选择上传后立即生成预览缓存。
- 记录上传历史与上传日志。
- 非管理员只能看到自己的上传历史/转码任务。

### 媒体缓存与转码

已实现：

- 静态图片生成 AVIF preview 与 AVIF thumb。
- GIF/APNG/动画 raster 生成 animated WebP preview 与 AVIF thumb。
- Pixiv ugoira zip 生成 animated WebP preview 与 AVIF thumb。
- 避免将 GIF/APNG 预览压成静态 AVIF。
- 预览缓存不存在时可回退原图。
- 详情接口返回原图、预览、缩略图文件大小。
- 转码任务记录：
  - status
  - stage
  - message
  - progress
  - frames done / total
  - fps
  - started / stage started / finished / updated 时间
  - error
- 管理页可查看转码进度和上传日志。
- 缓存缺失时可手动开始转码。
- 管理页轮询已优化：
  - 有运行中任务时 2.5 秒刷新。
  - 空闲时 15 秒刷新。
  - 页面隐藏时暂停。
  - 防止重复请求堆叠。
  - 完成任务固定耗时，不再显示“预计剩余：估算中”。

### 资源详情与文件响应

已实现：

- 获取 asset JSON 详情。
- 获取原图、预览、缩略图。
- 原图需要下载权限。
- 原图/预览响应使用 inline Content-Disposition，浏览器可直接打开支持的图片/动图。
- 下载按钮仍可通过前端 Blob 下载并保留文件名。
- 详情页可显示资源链接与文件大小。
- 不支持浏览器内联预览的文件类型提供下载入口。

### 删除与清理

已实现：

- 非管理员/普通编辑权限可发起删除请求。
- 删除请求会在 metadata / 数据库中标记为 `pending_cleanup`。
- 记录删除者用户名和用户 ID。
- 管理员可调用 cleanup 彻底删除待清理文件。
- 被标记删除的资源不再正常返回。

### 鉴权与账号

角色与权限：

- `guest`：浏览公开内容。
- `viewer`：浏览、下载、API 基础权限。
- `editor`：viewer + 上传、编辑标签、请求删除。
- `admin`：editor + 管理、彻底删除、创建用户、管理安全设置。

已实现：

- 账号密码登录。
- HttpOnly Cookie 会话。
- CSRF Token。
- Bearer API Token。
- 一个账号可拥有多个 API Token。
- 用户可查看/签发/撤销自己的 Token。
- 管理员可查看/签发/撤销他人 Token。
- API Token 记录最后使用时间和来源 IP。
- 用户可验证旧密码后重设新密码。
- CLI 可初始化管理员和重置密码。

### 安全模块

已实现：

- 全局并发限制。
- IP 并发限制。
- 用户并发限制。
- IP 每分钟请求数和流量限制。
- 用户每分钟请求数和流量限制。
- 按角色限制。
- 按具体用户限制。
- 上传大小限制。
- 可配置 trusted origins。
- 可配置是否信任代理头。
- 可选 viewer API whitelist。
- CSRF Origin 检查。
- 访问日志。
- 对高频正常轮询接口做 quiet log，减少日志膨胀。

## API 模块

主要 API：

- `GET /health`
- `GET /api/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/auth/password`
- `GET /api/search`
- `GET /api/img/random`
- `GET /api/img/{tag}`
- `GET /api/assets/{asset_key}`
- `GET /api/assets/{asset_key}/siblings`
- `GET /api/assets/{asset_key}/original`
- `GET /api/assets/{asset_key}/preview`
- `GET /api/assets/{asset_key}/thumb`
- `POST /api/assets/{asset_key}/tags`
- `DELETE /api/assets/{asset_key}`
- `DELETE /api/assets/{asset_key}/cleanup`
- `GET /api/tags/suggest`
- `GET /api/tags/catalog`
- `GET /api/tags/summary`
- `POST /api/tags/summary/export`
- `PUT /api/tags/{tag_name}/aliases`
- `POST /api/upload`
- `POST /api/rebuild`
- `POST /api/media/generate`
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
- `PATCH /api/pixiv-tokens/{token_id}`
- `DELETE /api/pixiv-tokens/{token_id}`
- `PATCH /api/pixiv-cookies/{cookie_id}`
- `DELETE /api/pixiv-cookies/{cookie_id}`

## 前端模块

### 页面

已实现页面：

- `/`：首页瀑布流/最新作品。
- `/files`：所有文件浏览与排序。
- `/search`：标签搜索、标签分组、随机入口。
- `/asset/[key]`：资源详情、预览、原图下载、资源链接、标签编辑、删除/清理入口。
- `/upload`：多文件上传、默认标签、别名编辑、上传队列状态。
- `/admin`：管理页。
- `/login`：账号密码登录。

### 组件

布局与通用组件：

- `SiteHeader`
- `SiteFooter`
- `UserMenu`
- `ThemeToggle`
- `LanguageSelect`
- `Button`
- `Input`
- `Label`
- `Badge`
- `Popover`
- `Dialog`
- `Spinner`
- `Skeleton`
- `TagChipInput`

图库组件：

- 瀑布流布局。
- 资产卡片。
- 无限滚动。
- 内容筛选开关。

Provider：

- QueryClient。
- Auth。
- Theme。
- Toast。
- Content preferences。
- Locale。

### 前端功能

已实现：

- Next.js rewrites 代理 `/api/*` 到后端。
- Cookie 会话登录。
- CSRF Token 自动附加到 unsafe 请求。
- 主题切换。
- R-18/R-18G 和 AI 内容偏好开关，并记住登录用户选择。
- 搜索页/首页/所有文件页内容筛选。
- 资源详情页原图下载和资源链接打开。
- 管理页上传历史、上传日志、转码任务、访问日志、安全设置、标签别名、用户、Token、重设密码。
- 管理页自动刷新优化。
- 管理页日志/缓存/转码提示本地化。

### 本地化

已实现轻量前端本地化：

- `frontend/src/lang/zh-CN.json`
- `frontend/src/lang/en-US.json`
- `frontend/src/lang/index.ts`
- `LocaleProvider`
- `LanguageSelect`

已接入本地化的区域：

- 顶部导航。
- 登录入口/用户菜单。
- 登录页。
- 主题切换。
- 管理页轮询状态。
- 管理页上传/转码日志。
- 管理页缓存状态。
- 管理页转码阶段、阶段详情、耗时、ETA。

其它页面可继续用 `useI18n().t("...")` 逐步迁移。

## 测试

已存在测试模块：

- `tests/test_api.py`
- `tests/test_auth.py`
- `tests/test_cli.py`
- `tests/test_db.py`
- `tests/test_media.py`
- `tests/test_pixiv_sync.py`
- `tests/test_storage.py`
- `tests/test_tags.py`

覆盖方向包括：

- API 行为。
- 鉴权和权限。
- CLI。
- 数据库重建与查询。
- 媒体缓存生成。
- Pixiv 同步。
- 存储与 metadata。
- 标签目录与搜索。

## 当前边界与后续方向

对照 `Analysis_v1.md`，当前实现已经满足 V1 的核心图库要求：原图不可变归档、metadata 可重建、标准标签/别名、多标签搜索、随机图 API、Pixiv 同步、多用户权限、展示缓存可重建和 ImageFlow 风格前端。仍未完全完成或尚未验证的部分包括：10 万图片规模基准测试、内置定时 Pixiv 同步、Redis、S3、完整 PWA Service Worker、相似标签推荐前端体验。

当前仍可继续增强的方向：

- 将更多前端页面全文迁移到本地化字典。
- 为管理页复杂表单继续拆分组件。
- 为安全设置提供更细的策略预设。
- 为大批量转码提供任务队列持久化和并发 worker 管理。
- 为日志提供更丰富的过滤和导出。
- 为标签系统补充更多默认目录和社区维护流程。
- 为生产部署补充反向代理、HTTPS、备份与恢复方案。
