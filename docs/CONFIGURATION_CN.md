# NyaGallery 配置与解析规则

配置模板为仓库根目录的 [`config.example.toml`](../config.example.toml)。运行时可通过 `--config` 或 `NYAGALLERY_CONFIG` 指定文件；若两者都没有，程序只会读取当前目录下的 `nyagallery.toml`（不存在则使用默认值）。TOML 由 Python `tomllib` 解析，类型错误不会被当作字符串静默接受。

## 1. 覆盖优先级

对于同一个配置项，优先级是：

```text
命令行参数 > 环境变量 > TOML 文件 > 内置默认值
```

CLI 的全局 `--storage`、`--database-url`、`--network-proxy` 会覆盖配置；`serve` 的 host/port/access-log 也可由环境变量覆盖。配置文件保存的秘密值会先解密，再由环境变量覆盖。

```bash
NYAGALLERY_CONFIG=/etc/nyagallery/nyagallery.toml \
NYAGALLERY_STORAGE=/srv/nyagallery/storage \
nyagallery serve --host 127.0.0.1
```

环境变量使用进程启动时的值。管理页保存 TOML 后需要重启 API 才能让所有启动期配置生效；数据库中的安全设置按 API 运行时读取。

解析流程可以概括为：定位配置文件 → 用 TOML 读取顶层表 → 转换为不可变配置对象并应用边界校验 → 应用环境变量覆盖 → 启动 CLI/API。配置对象生成后，CLI 会把核心值同步到兼容旧模块的环境变量；这不会反向修改 TOML 文件。

## 2. 核心段

```toml
[core]
storage = "/srv/nyagallery/storage"
database_url = "sqlite:////srv/nyagallery/storage/nyagallery.db"
tag_catalog_path = "/srv/nyagallery/storage/tags/catalog.json"
name_media_by_post_id = true

[server]
host = "127.0.0.1"
port = 8001
access_log = false
secure_cookies = true

[site]
app_name = "NyaGallery"
logo_url = ""
layout = ""
project_homepage = "https://github.com/NayaCcR/NyaGallery"
repository = "https://github.com/NayaCcR/NyaGallery"
icp_beian = ""
```

`storage` 是 metadata、缓存和默认 local 原图目录的根；自定义 local 策略可以把原图放在另一个目录。SQLite URL 中的四个 `/` 表示绝对路径。`secure_cookies` 只应在 HTTPS 部署启用。

## 3. 原图存储策略

```toml
[original_storage]
default_strategy = "local"

[[original_storage.strategies]]
name = "data-disk"
type = "local"
root_path = "/data/nyagallery/original"
timeout_seconds = 60
```

local 的 `root_path` 是运行后端机器上的目录：Linux 使用 `/data/...`，Windows 推荐 `D:/NyaGallery/original`。路径会用 `Path(...).expanduser().resolve()` 解析；留空表示使用默认 `storage/original`。上传时会创建缺少的父目录，但服务账户必须有权限。

远端策略的通用字段是 `prefix`、`endpoint`、`bucket`、`region`、凭据字段和 `timeout_seconds`。支持 `webdav`、`upyun`、`aliyun_oss`、`s3`（AWS/MinIO/R2）和 `onedrive`；不同后端所需字段见模板。不要把 Windows 路径写到运行在 Linux 的容器里。

## 4. 来源和媒体参数

```toml
[pixiv]
refresh_token = ""
cookie = ""
default_request_delay_seconds = 1.0
max_concurrency = 1

[misskey]
host = "misskey.io"
default_request_delay_seconds = 1.0
page_size = 100
download_concurrency = 5

[fanbox]
default_request_delay_seconds = 1.0
page_size = 10
download_concurrency = 3
download_files = true

[media]
max_frame_pixels = 50000000
max_image_pixels = 100000000
max_animation_frames = 500
max_zip_uncompressed_bytes = 536870912
max_zip_frame_bytes = 67108864
max_video_bytes = 134217728
generation_timeout_seconds = 300
task_timeout_seconds = 300
max_concurrency = 2
preview_max_edge = 1800
thumb_max_edge = 420
avif_quality = 82
webp_quality = 82
```

媒体上限同时是资源消耗和拒绝服务防线。公网部署应先保持默认值，再根据内存和磁盘吞吐逐步调整；`avif_quality`、`webp_quality` 范围为 1–100。

`[x]` 还支持 `auth_token`、`ct0`、请求延迟、`page_size`、`download_concurrency` 以及四个 GraphQL operation id；除非 X 接口变更，否则保持模板默认 operation id。`[developer]` 的 `config_editor_enabled` 默认开启，`console_enabled` 默认关闭。

## 5. 网络代理和 Redis

```toml
[network]
default_proxy = "direct"

[[network.proxies]]
name = "egress"
url = "http://127.0.0.1:7890"
auth_enabled = false

[[network.sources]]
source = "pixiv"
proxy = "egress"

[redis]
url = "redis://127.0.0.1:6379/0"
key_prefix = "nyagallery"
security_limiter = true
```

`NYAGALLERY_NETWORK_PROXY` 会覆盖部署级默认代理，但不会删除文件中的代理档案。Redis 的 `security_limiter` 只控制共享安全限流状态，不会把 SQLite 或文件存储迁移到 Redis。

## 6. 凭据与秘密

生成密钥：

```bash
nyagallery generate-secret-key
```

把结果放入 `NYAGALLERY_SECRET_KEY` 或 `[security].secret_key`。Pixiv、Misskey、X、Fanbox、代理和远端存储的秘密在有密钥时会加密保存；密钥丢失后只能重新录入凭据。不要把包含明文 token 的配置提交到 Git，服务配置文件建议仅服务账户可读。

## 7. 环境变量速查

常用变量包括：`NYAGALLERY_CONFIG`、`NYAGALLERY_STORAGE`、`NYAGALLERY_DATABASE_URL`、`NYAGALLERY_TAG_CATALOG`、`NYAGALLERY_HOST`、`NYAGALLERY_PORT`、`NYAGALLERY_ACCESS_LOG`、`NYAGALLERY_SECURE_COOKIES`、`NYAGALLERY_SECRET_KEY`、`NYAGALLERY_REDIS_URL`、`NYAGALLERY_REDIS_SECURITY_LIMITER`、`NYAGALLERY_NETWORK_PROXY`、`PIXIV_REFRESH_TOKEN`、`PIXIV_COOKIE`、`MISSKEY_TOKEN`、`X_AUTH_TOKEN`、`X_CT0`、`FANBOXSESSID`。

媒体环境变量以 `NYAGALLERY_MEDIA_` 开头，例如 `NYAGALLERY_MEDIA_MAX_IMAGE_PIXELS`、`NYAGALLERY_MEDIA_MAX_CONCURRENCY`；它们覆盖 `[media]` 同名项。完整字段和默认值以 `config.example.toml` 及 `src/nyagallery/config.py` 为准。

## 8. 安全配置的边界

`[developer]` 仅控制配置编辑器和受控开发者控制台，生产环境建议关闭 `console_enabled`。安全限流、trusted origins、viewer API 白名单等运行时设置通过管理 API 或 `security-config` CLI 调整；不要把管理 API 暴露给未认证用户。
