# NyaGallery 数据契约

## 统一 Asset

统一交换格式为 `nyagallery.asset.v1`。`asset_id` 是 `sha256:<64 位十六进制摘要>`；原图的 `blob.sha256` 必须与它一致。`blob.storage_key` 是人类可读的稳定路径，原图不可变，分类变化不能移动它。

```json
{
  "schema": "nyagallery.asset.v1",
  "asset_id": "sha256:<sha256>",
  "blob": {
    "sha256": "<sha256>",
    "size": 123,
    "mime": "image/jpeg",
    "width": 1920,
    "height": 1080,
    "storage_key": "original/pixiv_123.jpg",
    "original_filename": "123.jpg"
  },
  "metadata": {},
  "external_refs": [{"system": "lsky", "id": "123", "path": "uploads/123.jpg"}],
  "created_at": "2026-01-01T00:00:00Z"
}
```

## Primary 模式

`file` 模式以 JSON 元数据为真相源，数据库只允许作为可删除、可重建的索引；`database` 模式以 SQLite、PostgreSQL 或 MySQL 为真相源，JSON 只能作为导出侧车。应用不会在一次写入中双写两个 primary。

`nyagallery convert --from file|database --to file|database` 默认只做 dry-run；切换到 `file` 时需要 `--output <dir>`，加入 `--confirm` 后才会在目标旁边创建备份，写入临时目录，逐文件计算 SHA256，再原子切换。切换到 `database` 会校验原图 SHA256 后在一个事务内导入索引，并保存数据库侧车备份。源文件始终只读。

## 资产时间字段

`published_at`、`captured_at`、`uploaded_at`、`scraped_at` 是可选时间字段；写入、导出和往返时统一为带 `Z` 的 UTC ISO 8601 微秒精度。缺失值保持 `null`，序列化时允许省略，不得用其他事件时间伪造。file/database 两种后端导出都保留显式值。历史排序中的 `uploaded_at` 仍表示入库/抓取时间（legacy `crawl_time`），真实上传事件使用 `upload_timestamp` 排序。资产时间线按所选字段实际值排序；字段缺失时按既定回退表达式定位，但响应中的显式字段不会被填充，无法解析的值归入未知时间。

## 旧数据

`nyagallery.creator_metadata.v1` 由 `LegacyReader` 只读解析。启动和索引重建仍能读取旧的单资源 JSON 及 creator 分组 JSON，不自动覆盖旧文件。显式转换或 `migrate-metadata` 才会写新文件。

## 物理与虚拟层

物理层保存来源、创作者和作品 ID；虚拟文件夹保存 tag 查询（例如 `tag:type/ugoira`），位于 `storage/tags/virtual_folders.json`，不会移动原图。来源、画师、类型、相册和自建分类都应通过 tag/query 表达。

## 迁移与回滚

Importer 先读取源、转换 Asset、只读校验 SHA256，再复制或硬链接原图，保留 `external_refs`。目标写入失败时不修改源；目标目录可使用转换命令生成的备份恢复。Lsky importer 重新计算 SHA256，不把源数据库表直接复制到目标库。

## Share Link

分享链接保存 `token_hash`、可选 `password_hash`、`expires_at`、`revoked_at`、访问计数和访问时间；secret 只在创建响应返回。访问日志保存 link、asset、状态、时间、截断 User-Agent 和受控客户端地址，不保存 token 或密码。公开分享仍执行 guest 敏感内容策略。

取图短链接保存唯一 `slug`、资源 ID、创建者、可选 `expires_at` 和 `revoked_at`；自定义 slug 只允许字母、数字、下划线和连字符，冲突返回 409。短链接不保存 secret，公开解析默认返回 preview，`original=true` 才返回原图，并沿用过期、撤销和 guest 敏感内容策略。

通用访问日志保存可选 `asset_key` 和 `access_type`。资源 API 的访问类型为 `metadata`、`preview`、`thumb`、`original` 或 `api_examples`；短链接和分享链接分别记录为 `short_link`、`share_link`。日志仍受启用开关和 retention 清理策略控制，查询可按资源、用户、类型和时间范围筛选。

分块上传会话保存在 storage 根目录的 `chunked/{upload_id}`，manifest 记录文件名、总大小、分块数、可选 SHA-256、MIME 和创建用户；分块支持乱序与重复覆盖，完成时缺块、大小或摘要不匹配会拒绝提交，成功后删除临时会话并复用普通上传元数据流程。

资产评论保存 `asset_key`、作者用户 ID/用户名、正文、创建/更新时间和软删除时间。读取沿用资源 ACL 与游客敏感内容策略；创建需要登录，编辑和删除限评论作者或 admin，删除只写入 `deleted_at`，不会立即清除数据库记录。

资产点赞以 `asset_key + user_id` 唯一约束保存，接口返回总数和当前用户状态；添加和移除操作幂等，读取沿用资源 ACL，写入需要登录。

评论中的 `@username` 会按不区分大小写匹配启用用户，提及关系以 `comment_id + user_id` 唯一约束保存；未知用户和重复提及不生成关系，编辑正文时会重建关系。匹配到的其他用户会在 `mention_enabled` 开启时收到 `comment_mention` 通知；通知保存接收者、触发者、资源/评论引用、消息、已读时间和创建时间，列表和标记已读接口只允许访问当前用户数据。用户通知偏好默认开启，并保存 mention/like 两类开关。

API Token 响应只包含 `token_prefix`、`label`、`scopes`、使用时间和撤销状态等元数据，不包含 secret、hash 或完整 Token。`scopes: null` 表示兼容旧行为，按用户当前 role 权限计算；非 null 时为规范化权限名数组，且不能超过调用者和目标角色权限。旧数据库初始化时自动增加 scopes 字段。
