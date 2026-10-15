# NyaGallery API 参考

后端默认地址为 `http://127.0.0.1:8001`。生产环境建议通过 Next.js/nginx 同源访问。成功响应通常是 JSON；文件接口返回 `image/*` 或原始 MIME。错误响应为 `{"detail":"..."}`。

FastAPI 同时提供交互式 OpenAPI 页面：`/docs`（Swagger UI）、`/redoc`（ReDoc）和 `/openapi.json`。生产环境建议只在内网或管理员访问范围内开放这些页面。

## 1. 鉴权

正式角色值为 `guest`、`viewer`、`editor`、`admin` 和 `developer`；`dev` 不是角色名，只能作为普通用户名使用。角色权限如下：

| 角色 | 权限标识 | 能力概览 |
| --- | --- | --- |
| `guest` | `view` | 浏览公开资源；敏感分级和 AI 内容按偏好/策略隐藏 |
| `viewer` | `view`, `download`, `api` | 浏览、搜索、下载和查看自己的历史 |
| `editor` | `view`, `download`, `api`, `upload`, `edit_tags`, `delete_request` | 增加上传、编辑资源标签、发起删除和生成缓存 |
| `admin` | `view`, `download`, `api`, `upload`, `edit_tags`, `delete_request`, `delete`, `admin` | 增加清理资源、重建、用户、安全、凭据和配置管理 |
| `developer` | `view`, `download`, `api`, `upload`, `edit_tags`, `delete_request`, `delete`, `admin`, `developer`, `config`, `console` | 继承 admin 能力，并增加配置编辑器和受控维护台 |

`developer` 是最高信任级别。admin 不能创建 developer 用户；只能通过本机 CLI 或已有 developer 用户创建。`GET /api/access/permission-groups` 可由 admin 及以上角色读取上述权限组。这里的角色权限组与 `/api/access/groups` 管理的资源共享访问组不是同一概念。

网页登录使用 Cookie：

```http
POST /api/auth/login
Content-Type: application/json

{"username":"admin","password":"...","remember":true}
```

响应包含 `csrf_token`，服务端同时设置 `nya_session`（HttpOnly）和 `nya_csrf`。所有 POST/PUT/PATCH/DELETE 请求发送 `X-CSRF-Token`。脚本使用：

```http
Authorization: Bearer nya_xxxxx
```

注册入口由安全设置项 `registration_mode` 控制，取值为 `closed`（默认，仅管理员创建）、`open`（游客自助注册）和 `invite`（必须携带邀请码）。`GET /api/auth/registration` 无需鉴权，供登录页判断是否展示注册表单：

```http
GET /api/auth/registration

{"mode":"open","enabled":true,"invite_required":false,"default_role":"viewer","username_min_length":3,"username_max_length":64,"password_min_length":8}
```

`POST /api/auth/register` 同样无需鉴权，成功时直接创建 `viewer` 用户并写入登录 Cookie（响应结构与登录一致）。用户名限 3-64 位字母、数字、下划线、点和短横线，密码至少 8 位；用户名重复返回 `409`，关闭注册返回 `403`，邀请码无效返回 `400`。

```http
POST /api/auth/register
Content-Type: application/json

{"username":"cat","password":"...","remember":true,"invite_code":"nyi_xxx"}
```

## 2. 基础与浏览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康和存储/Redis 状态 |
| GET | `/api/site/config` | 站点名称、logo、备案和布局 |
| GET | `/api/me` | 当前用户、角色、权限和鉴权方式 |
| GET | `/api/me/api-addresses` | 需要 api 权限；返回当前请求 Host 下的资源 metadata、preview、thumb、original 和短链接创建地址模板及所需 scope |
| GET | `/api/storage/strategies` | 当前用户可用的原图策略 |
| GET | `/api/search?q=tag&limit=50&offset=0&sort=asset_key&order=asc` | 资源搜索 |
| GET | `/api/posts?source=misskey_io&limit=20&offset=0` | 帖子列表 |
| GET | `/api/posts/{post_key}` | 帖子详情及附件 |
| GET | `/api/assets/{asset_key}` | 资源 metadata、标签和文件 URL |
| GET | `/api/assets/{asset_key}/siblings` | 同一作品的多页资源 |
| GET | `/api/img/random?q=tag&original=false` | 随机预览；`original=true` 返回原图 |
| GET | `/api/img/{tag}?original=false` | 按标签随机资源 |

`/api/search` 的 `limit` 最大 200，帖子列表最大 100。搜索支持空格分隔的 AND、`-tag` 排除、alias 和 `filename:` 查询。返回分页字段 `items`、`limit`、`offset`；帖子额外返回 `total` 和 `has_more`。

文件路径：

```text
GET /api/assets/{asset_key}/original   # viewer 及以上，下载权限
GET /api/assets/{asset_key}/preview    # 公开可见资源
GET /api/assets/{asset_key}/thumb      # 公开可见资源
```

`/api/img/random` 和 `/api/img/{tag}` 支持 `original=true`；该参数仍可匿名返回非敏感资源原图，生产环境如只想公开预览图，应在反向代理或后端策略中禁止该参数。游客随机查询会排除 `rating:r18` / `rating:r18g`，并同时检查资源的 `age_rating` 字段。

## 3. 标签和资源维护

| 方法 | 路径 | 权限/请求体 |
| --- | --- | --- |
| GET | `/api/tags/suggest?q=cat&limit=20` | viewer；标签建议 |
| GET | `/api/tags/catalog` | viewer；完整标签目录 |
| GET | `/api/tags/summary` | viewer；标签计数 |
| POST | `/api/tags/summary/export` | admin；写出 `tags/summary.json` |
| PUT | `/api/tags/{tag_name}/aliases` | admin；`{"aliases":["旧名"]}` |
| PUT | `/api/tags/{tag_name}/relations` | admin；`{"implications":["上位标签"],"suggestions":["相关标签"]}`；循环关系返回 400 并保留原状态 |
| POST | `/api/assets/{asset_key}/share-links` | owner/admin 创建资源分享链接，可选公开、密码、过期时间；secret 只在创建响应返回 |
| GET | `/api/assets/{asset_key}/share-links` | owner/admin 列出分享链接元数据，不返回 secret/hash |
| DELETE | `/api/share-links/{link_id}` | owner/admin 撤销分享链接 |
| POST | `/api/assets/{asset_key}/short-links` | owner/admin 创建取图短链接，可选 3-80 位自定义 slug 和过期时间；slug 只能含字母、数字、下划线和连字符 |
| GET | `/api/assets/{asset_key}/short-links` | owner/admin 列出短链接及过期/撤销状态 |
| DELETE | `/api/short-links/{link_id}` | owner/admin 撤销短链接 |
| GET | `/s/{slug}` | 无需登录；返回预览文件，追加 `?original=true` 返回原图；过期、撤销或游客敏感内容返回错误 |
| GET | `/api/share-links/logs` | admin 分页查看分享访问状态、资源、时间和截断客户端信息 |
| GET | `/api/share/{token}` | 按分享 token 访问资源 metadata；密码通过 HTTPS query/body 传入，公开链接仍受敏感内容策略 |
| GET | `/api/share/{token}/preview` | 按分享 token 访问 preview |
| GET | `/api/share/{token}/original` | 按分享 token 访问原图 |
| GET/POST | `/api/assets/{asset_key}/comments` | 需要 view；读取或创建资产评论，创建需要登录；支持 `limit`/`offset` |
| PATCH/DELETE | `/api/assets/{asset_key}/comments/{comment_id}` | 需要 view；评论作者或 admin 可编辑/软删除评论；正文中的 `@username` 会解析为现有启用用户 |
| GET | `/api/assets/{asset_key}/likes` | 需要 view；返回点赞总数和当前用户是否已点赞 |
| PUT/DELETE | `/api/assets/{asset_key}/likes` | 需要登录且有 view；幂等地添加或移除当前用户的点赞 |
| GET | `/api/notifications` | 需要登录；分页读取当前用户通知，支持 `unread_only=true` |
| POST | `/api/notifications/read` | 需要登录；将指定通知或当前用户全部未读通知标记为已读 |
| POST | `/api/assets/{asset_key}/tags` | editor；`{"canonical_tags":["character:…"]}` |
| POST | `/api/assets/{asset_key}/acl/groups` | owner/admin 将资源绑定到群组，权限为 view/edit/upload |
| DELETE | `/api/assets/{asset_key}/acl/groups/{group_id}` | owner/admin 解除资源与群组绑定 |
| DELETE | `/api/assets/{asset_key}` | editor；标记 `pending_cleanup` |
| DELETE | `/api/assets/{asset_key}/cleanup` | admin；永久删除文件和 metadata |

删除分两步：普通删除只标记，管理员 cleanup 才会删除原图；已 cleanup 的资源只能从备份恢复。

## 4. 上传、缓存和重建

上传使用 multipart：

```bash
curl -X POST http://127.0.0.1:8001/api/upload \
  -H "Authorization: Bearer nya_xxxxx" \
  -F "file=@image.jpg" \
  -F 'title=Example' \
  -F 'canonical_tags=general:sample' \
  -F 'generate_cache=true'
```

`canonical_tags` 是空格分隔的 canonical tag 字符串；`tag_aliases` 如需同时维护别名则传 JSON 对象，例如 `{"general:sample":["sample"]}`。上传响应返回资源详情，若 `generate_cache=true` 还会返回排队中的 `transcode_job_id`。

浏览器上传可附带 `last_modified_ms`（`File.lastModified`，整数 Unix 毫秒）；范围为 1980-01-01 至服务器当前时间后 24 小时，格式、单位或范围不合法返回 422。该字段可省略，旧客户端仍可上传。

资源响应包含 `published_at`、`captured_at`、`uploaded_at`、`scraped_at` 四个可选 ISO 8601 时间字段；`GET /api/timeline` 提供仅基于资产的 UTC 日历时间线，支持 `published_at`、`captured_at`、`uploaded_at`、`scraped_at` 和 `upload_timestamp`，服务端先按时间上界筛选再分页，返回 `timeline_time` 供客户端分组；`uploaded_at` 保持历史语义（crawl time），`upload_timestamp` 才是真实上传时间。时间线沿用图库权限和 guest 敏感内容过滤，未知时间归入客户端的未知时间组。posts 的独立正文时间线尚未纳入；旧资源会在数据库初始化时补齐可确定的来源事件，缺失值保持为空。搜索支持 `sort=published_at|captured_at|scraped_at|upload_timestamp`，排序缺失时按入库/抓取时间回退，但不会向响应填入推断值。`captured_at` 为带偏移的 ISO 8601，`captured_at_source` 为 `exif:DateTimeOriginal` / `exif:DateTimeDigitized` / `exif:DateTime` / `browser_last_modified` / `file_mtime`。EXIF 时间另存 `exif_captured_at`，`captured_at_timezone_source` 标识 `exif_offset` 或 `configured_default`；`camera` 包含 `make` / `model`，`gps.latitude` / `gps.longitude` 为十进制度（南纬、西经为负，缺损坐标省略）。时间按上述 EXIF 优先级选择有效值，使用对应 OffsetTime；缺失或非法偏移使用 `[media].exif_timezone`。无有效 EXIF 时间时回退浏览器原文件时间；本地 CLI 导入使用源文件 mtime。远程上传或旧客户端未提供原时间时保持缺失，不使用服务器新文件 mtime，也不覆盖 `artwork_date`。Pillow 缺失或文件无法解析不阻断上传。

`GET /api/assets/{asset_key}/api-examples` 返回基于当前请求 Host 的 curl/fetch/python 示例，不包含真实 Token。元数据和 preview/thumb 需要 `view` scope，原图需要 `download` scope；示例中的占位 Token 必须由调用者通过 API Key 管理页面或签发接口获得。

远程图片可通过 `POST /api/upload/url` 提交 JSON：

```json
{"url":"https://example.org/image.jpg","title":"Example","generate_cache":true}
```

端点要求 upload 权限，只接受 HTTP(S) URL 和声明为 `image/*` 的成功响应；拒绝 URL 用户信息及所有重定向。DNS 返回的全部地址必须为全局可路由单播地址（含 IPv4 映射地址检查），连接固定使用其中一个已验证 IP；HTTPS 仍按原域名执行 SNI 和证书验证，不读取环境代理。最大响应为 100 MiB，并受站点上传大小限制约束；连接/读写超时 10 秒，DNS 等待及下载共用 30 秒总时限。下载在线程执行，网络错误只返回通用信息，原始 URL 继续保存在 `original_url`。批量 URL 由客户端逐条调用，失败项可单独重试；写入后沿用 SHA-256 重复检测。MIME 检查依据上游响应头，不等同于完整图片解码验证。

主要接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/upload` | 上传原图，可选作者、标题、标签、存储策略和缓存 |
| POST | `/api/upload/url` | 拉取单个远程 http/https 图片并按上传流程入库；需 upload 权限，仅允许公网图片目标 |
| POST | `/api/upload` | multipart 支持多文件和 ZIP；目录拖放由前端展开为多个文件请求 |
| POST | `/api/media/generate` | editor 生成全部或指定 `asset_key` 缓存 |
| POST | `/api/rebuild` | admin 从 metadata 重建数据库；`{"generate_cache":true}` 可连带缓存 |
| GET | `/api/uploads/history` | 当前用户上传历史，admin 可看全部 |
| GET | `/api/uploads/logs` | 上传/转码日志；返回 uploader、时间、状态、事件、消息、extra（来源/任务/错误等）和文件指纹相关资源字段 |
| GET | `/api/transcode/jobs` | 转码任务 |
| POST | `/api/transcode/assets/{asset_key}/start` | editor 启动单资源转码 |
| POST | `/api/transcode/cancel-all` | admin 取消运行中的转码 |

## 5. 同步接口

Pixiv：`GET /api/sync/pixiv/config`、`POST /api/sync/pixiv/{pid}`、`POST /api/sync/pixiv/user/{uid}`、`POST /api/sync/pixiv/bookmarks/{uid}`。管理页 PID 输入支持纯 ID、Pixiv artworks URL、`member_illust.php?illust_id=...` 和以空格/逗号/换行分隔的批量输入，每个 ID 独立调用单作品同步接口。OAuth 使用 `/api/sync/pixiv/oauth/start`、`/exchange`、`/browser-login` 和 visible session 接口；浏览器扩展可调用 `/api/sync/pixiv/session/exchange`。

Misskey：`GET /api/sync/misskey/config`、`GET /api/sync/misskey/logs`、`POST /api/sync/misskey/user/{username}`。

Fanbox：`GET /api/sync/fanbox/config`、`GET /api/sync/fanbox/logs`、`POST /api/sync/fanbox/login`、`POST /api/sync/fanbox/creator/{creator_id}`、`POST /api/sync/fanbox/posts`。

X：`GET /api/sync/x/config`、`GET /api/sync/x/logs`、`POST /api/sync/x/posts`、`POST /api/sync/x/user/{screen_name}`。

同步请求的分页、并发、延迟、是否下载媒体和 `storage_strategy` 字段与 CLI 同名；推荐先用 CLI `--dry-run` 或小 limit 验证凭据和代理，再扩大范围。

## 6. 管理、凭据与安全

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST/GET | `/api/users` | admin 创建/列出用户 |
| POST | `/api/users/{username}/password` | admin 重设密码 |
| POST/GET | `/api/users/{username}/token(s)` | 签发/列出 Bearer Token，可选 `scopes` 权限集合；不能超出调用者和目标角色权限 |
| PATCH | `/api/tokens/{token_id}` | 更新 Token scopes，撤销/角色降级立即影响有效权限 |
| DELETE | `/api/tokens/{token_id}` | 撤销 Token |
| GET | `/api/access/permission-groups` | admin；列出 `viewer`、`editor`、`admin`、`developer` 及其权限标识 |
| GET/POST | `/api/access/groups` | admin；列出或创建资源共享访问组，创建请求为 `{"name":"组名","member_usernames":["alice"]}` |
| PUT/DELETE | `/api/access/groups/{group_id}` | admin；更新自己创建的共享访问组或将其删除 |
| POST | `/api/assets/acl/groups/bulk` | editor；将最多 500 个 `asset_keys` 批量绑定到自己拥有的分享组，权限为 `view`、`edit` 或 `upload`；资源和群组全部通过校验后整体提交 |
| POST/DELETE | `/api/assets/{asset_key}/acl/groups[/{group_id}]` | editor；为单个自有资源绑定分享组权限或解除该组的所有授权 |
| GET/PUT | `/api/security/settings` | admin 安全策略和限流，含注册入口 `registration_mode` |
| GET | `/api/security/access-logs` | admin 访问日志；支持 `q`、`asset_key`、`user_id`、`access_type`、`created_after` 和 `created_before` 筛选；资源 API 请求会记录资源 ID与 metadata/preview/thumb/original/api_examples 类型 |
| GET/POST | `/api/registration/invites` | admin；列出或生成注册邀请码，创建请求为 `{"label":"...","code":null,"max_uses":1,"expires_in_days":null}`，响应中的 `code` 仅在创建时返回一次 |
| DELETE | `/api/registration/invites/{invite_id}` | admin；作废邀请码（已使用的次数不受影响） |
| GET/PUT | `/api/developer/config` | developer 配置编辑器 |
| GET | `/api/developer/console` | developer 受控维护台 |
| POST | `/api/developer/console/reset-password` | developer；维护台启用时重设用户密码，请求为 `{"username":"alice","new_password":"..."}` |

创建用户时提交 `{"username":"...","password":"...","role":"viewer"}`。admin 可以创建 `guest`、`viewer`、`editor` 和 `admin`，但只有 developer 或本机 CLI 可以创建 `developer`。

Pixiv、X、Misskey、Fanbox 凭据接口均挂在 `/api/users/{username}/...` 下，列表只返回脱敏摘要；不要把响应中的 token 写入日志。

## 7. 兼容性和排错

`/api/login`、`/api/logout`、`/api/password` 是旧别名，优先使用 `/api/auth/*`。遇到 `401` 检查 Token/会话，`403` 检查角色、CSRF 或 trusted origin，`404` 检查 asset key/路由版本，`413` 检查上传限制，`429` 检查限流和 Redis。先请求 `/health`，再确认前端的 `NYA_API_BACKEND` 指向同一版本后端。
