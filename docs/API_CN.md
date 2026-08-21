# NyaGallery API 参考

后端默认地址为 `http://127.0.0.1:8001`。生产环境建议通过 Next.js/nginx 同源访问。成功响应通常是 JSON；文件接口返回 `image/*` 或原始 MIME。错误响应为 `{"detail":"..."}`。

FastAPI 同时提供交互式 OpenAPI 页面：`/docs`（Swagger UI）、`/redoc`（ReDoc）和 `/openapi.json`。生产环境建议只在内网或管理员访问范围内开放这些页面。

## 1. 鉴权

- 游客：可浏览公开资源，自动隐藏敏感分级和 AI 内容（取决于偏好/策略）。
- `viewer`：浏览、搜索、下载和查看自己的历史。
- `editor`：增加上传、编辑资源标签、发起删除和生成缓存。
- `admin`：增加清理资源、重建、用户、安全、凭据和配置管理。

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

## 2. 基础与浏览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康和存储/Redis 状态 |
| GET | `/api/site/config` | 站点名称、logo、备案和布局 |
| GET | `/api/me` | 当前用户、角色、权限和鉴权方式 |
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
| PUT | `/api/tags/{tag_name}/labels` | admin；`{"labels":{"zh-CN":"…","en-US":"…"}}` |
| POST | `/api/assets/{asset_key}/tags` | editor；`{"canonical_tags":["character:…"]}` |
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

主要接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/upload` | 上传原图，可选作者、标题、标签、存储策略和缓存 |
| POST | `/api/media/generate` | editor 生成全部或指定 `asset_key` 缓存 |
| POST | `/api/rebuild` | admin 从 metadata 重建数据库；`{"generate_cache":true}` 可连带缓存 |
| GET | `/api/uploads/history` | 当前用户上传历史，admin 可看全部 |
| GET | `/api/uploads/logs` | 上传/转码日志 |
| GET | `/api/transcode/jobs` | 转码任务 |
| POST | `/api/transcode/assets/{asset_key}/start` | editor 启动单资源转码 |
| POST | `/api/transcode/cancel-all` | admin 取消运行中的转码 |

## 5. 同步接口

Pixiv：`GET /api/sync/pixiv/config`、`POST /api/sync/pixiv/{pid}`、`POST /api/sync/pixiv/user/{uid}`、`POST /api/sync/pixiv/bookmarks/{uid}`。OAuth 使用 `/api/sync/pixiv/oauth/start`、`/exchange`、`/browser-login` 和 visible session 接口；浏览器扩展可调用 `/api/sync/pixiv/session/exchange`。

Misskey：`GET /api/sync/misskey/config`、`GET /api/sync/misskey/logs`、`POST /api/sync/misskey/user/{username}`。

Fanbox：`GET /api/sync/fanbox/config`、`GET /api/sync/fanbox/logs`、`POST /api/sync/fanbox/login`、`POST /api/sync/fanbox/creator/{creator_id}`、`POST /api/sync/fanbox/posts`。

X：`GET /api/sync/x/config`、`GET /api/sync/x/logs`、`POST /api/sync/x/posts`、`POST /api/sync/x/user/{screen_name}`。

同步请求的分页、并发、延迟、是否下载媒体和 `storage_strategy` 字段与 CLI 同名；推荐先用 CLI `--dry-run` 或小 limit 验证凭据和代理，再扩大范围。

## 6. 管理、凭据与安全

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST/GET | `/api/users` | admin 创建/列出用户 |
| POST | `/api/users/{username}/password` | admin 重设密码 |
| POST/GET | `/api/users/{username}/token(s)` | 签发/列出 Bearer Token |
| DELETE | `/api/tokens/{token_id}` | 撤销 Token |
| GET/PUT | `/api/security/settings` | admin 安全策略和限流 |
| GET | `/api/security/access-logs` | admin 访问日志 |
| GET/PUT | `/api/developer/config` | developer 配置编辑器 |
| GET | `/api/developer/console` | developer 受控维护台 |

Pixiv、X、Misskey、Fanbox 凭据接口均挂在 `/api/users/{username}/...` 下，列表只返回脱敏摘要；不要把响应中的 token 写入日志。

## 7. 兼容性和排错

`/api/login`、`/api/logout`、`/api/password` 是旧别名，优先使用 `/api/auth/*`。遇到 `401` 检查 Token/会话，`403` 检查角色、CSRF 或 trusted origin，`404` 检查 asset key/路由版本，`413` 检查上传限制，`429` 检查限流和 Redis。先请求 `/health`，再确认前端的 `NYA_API_BACKEND` 指向同一版本后端。
