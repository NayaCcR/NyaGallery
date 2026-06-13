# NyaGallery 使用文档

本文档面向本地开发和自部署使用，覆盖后端、前端、Pixiv 同步、媒体缓存、用户权限和常见维护流程。

文档导航：[中文首页](README_CN.md) | [中文完整说明](READMORE_CN.md) | [快速启动](QUICKSTART_CN.md) | [实现总结](summary.md) | [前端说明](../frontend/README.md) | [英文首页](../README.md)。

## 1. 环境要求

- Python 3.11 或更新版本
- Node.js 18 或更新版本
- npm
- 可选：PostgreSQL
- 可选：Redis
- 可选：Pixiv refresh token

默认示例使用 PowerShell，并假设当前目录是项目根目录：

```powershell
cd E:\Code\NyaGallery
```

## 2. 安装后端

开发/本地使用建议一次安装全部常用后端依赖：

```powershell
python -m pip install -e ".[dev,media,pixiv,pixiv-login]"
```

如果你在 conda 环境里工作，先进入对应环境再执行同样的 pip 安装即可；`nyagallery` 命令会被安装到当前 conda 环境的 `Scripts/` 目录：

```powershell
conda activate your-env
python -m pip install -e ".[dev,media,pixiv,pixiv-login]"
nyagallery --help
```

如果已经有 Pixiv refresh token，只需要抓取能力、不需要本地浏览器登录助手，可以安装较轻的组合：

```powershell
python -m pip install -e ".[dev,media,pixiv]"
```

如果不需要 Pixiv 同步，可以只安装：

```powershell
python -m pip install -e ".[dev,media]"
```

如果要使用 PostgreSQL：

```powershell
python -m pip install -e ".[postgres]"
```

如果要使用 Redis：
```powershell
python -m pip install -e ".[redis]"
```

## 3. 一键初始化

全新开始时，推荐直接使用一键初始化：

```powershell
nyagallery --storage storage setup
```

它会自动完成：

```text
创建 storage 目录
创建默认标签目录
迁移旧 metadata（如果有）
重建数据库索引
创建 admin 用户
签发 API Token
```

命令会要求输入管理员密码，并输出一个 `token`。前端登录页使用账号密码；输出的 API Token 主要给脚本、外部程序或旧客户端使用。

如果想显式指定用户名：

```powershell
nyagallery --storage storage setup --username admin --role admin
```

如果只是本地临时测试，也可以直接传密码：

```powershell
nyagallery --storage storage setup --username admin --role admin --password secret
```

默认目录结构：

```text
storage/
├─ original/     # 原始文件，永久保留，不覆盖
├─ preview/      # 预览缓存，可删除重建
├─ thumbs/       # 缩略图缓存，可删除重建
├─ metadata/     # 每个创作者一个 metadata JSON，内部包含 assets 数组
└─ tags/         # 标签目录 catalog.json
```

## 4. 手动初始化

如果你不想用 `setup`，也可以分步执行。

创建标签目录：

```powershell
nyagallery --storage storage init-tags
```

本地默认使用 SQLite，数据库文件会放在 `storage/nyagallery.db`。初始化或重建数据库：

```powershell
nyagallery --storage storage rebuild-db
```

如果你之前已经有旧版“每个资源一个 JSON”的 metadata，先迁移为“每个创作者一个 JSON”：

```powershell
nyagallery --storage storage migrate-metadata
```

使用 PostgreSQL 时传入 SQLAlchemy URL：

```powershell
nyagallery `
  --storage storage `
  --database-url "postgresql+psycopg://user:pass@localhost/nyagallery" `
  rebuild-db
```

数据库只保存索引、用户和 API Token。图库资产以 `original/` 与 `metadata/` 为准，因此数据库可以随时重建。

## 5. 手动创建管理员与 Token

创建管理员：

```powershell
nyagallery --storage storage create-user admin --role admin
```

签发 API Token：

```powershell
nyagallery --storage storage issue-token admin
```

保存输出的 Token。前端登录页使用账号密码；API Token 主要给脚本、外部程序或旧客户端使用。

角色权限：

```text
guest   可浏览
viewer  可浏览、下载、API 访问
editor  viewer 权限 + 上传、编辑标签、发起删除请求
admin   editor 权限 + 用户、同步、重建、彻底清理等管理操作
```

## 6. 启动后端 API

启动 FastAPI：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

也可以使用统一后端配置文件。复制模板后按需修改：

```powershell
Copy-Item config.example.toml nyagallery.toml
nyagallery --config nyagallery.toml serve
```

配置文件使用 TOML，包含核心存储、数据库、服务监听、站点信息和 Pixiv 默认值：

```toml
[core]
storage = "storage"
database_url = ""
tag_catalog_path = ""

[server]
host = "127.0.0.1"
port = 8001
access_log = false
secure_cookies = false

[site]
project_homepage = "https://github.com/NayaCcR/NyaGallery"
repository = "https://github.com/NayaCcR/NyaGallery"
icp_beian = ""

[pixiv]
refresh_token = ""
cookie = ""
default_request_delay_seconds = 1.0
max_concurrency = 1

[network]
default_proxy = "direct"

[[network.proxies]]
name = "direct"
url = ""
auth_enabled = false
username = ""
password = ""

[network.sources.pixiv]
proxy = "direct"

[redis]
url = ""
key_prefix = "nyagallery"
security_limiter = false
```

优先级为：命令行参数 > 环境变量 > 配置文件 > 默认值。`icp_beian` 留空时前端页脚不会显示备案号；填写后会通过 `/api/site/config` 暴露给前端页脚。后端不能直连某个来源时，可在 `[[network.proxies]]` 定义代理档案，再用 `[network.sources.pixiv]`、`[network.sources.x]`、`[network.sources.fanbox]` 等来源规则选择。`NYAGALLERY_NETWORK_PROXY` 或 `nyagallery --network-proxy http://127.0.0.1:7890 serve` 可作为部署级默认代理。

Redis 是可选分布式基础设施，默认关闭。安装：

```powershell
python -m pip install -e ".[redis]"
```

然后设置：

```toml
[redis]
url = "redis://127.0.0.1:6379/0"
key_prefix = "nyagallery"
security_limiter = true
```

打开 `security_limiter` 后，请求并发、频率和流量限制会使用 Redis 共享状态，适合多个后端实例挂在同一个反向代理后面。对应环境变量是 `NYAGALLERY_REDIS_URL`、`NYAGALLERY_REDIS_KEY_PREFIX` 和 `NYAGALLERY_REDIS_SECURITY_LIMITER`。

注意：`--storage storage` 是相对当前终端目录的路径。后端和 `set-password` 必须指向同一个 storage；如果你在 `frontend/` 目录里启动后端，应写成：

```powershell
nyagallery --storage ..\storage serve --host 127.0.0.1 --port 8001
```

可用 `/health` 检查后端实际使用的 storage 绝对路径：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

正常返回：

```json
{
  "ok": true,
  "storage": "E:\\Code\\NyaGallery\\storage"
}
```

## 7. 启动前端

安装前端依赖：

```powershell
cd frontend
npm install
```

启动开发服务器：

```powershell
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"
npm run dev
#npm run dev -- -H 0.0.0.0 -p 3000
```

打开：

```text
http://localhost:3000
```

进入登录页后使用账号密码登录。未登录时可以浏览公开内容；上传、管理、编辑标签需要对应账号权限。脚本请求可以继续使用第 5 步签发的 API Token。

## 8. Pixiv 同步

推荐使用 OAuth refresh token。管理页的 `OAuth` 选项可以启动一个可见 Pixiv 登录浏览器，由后端临时通过 `gppt`/Playwright 完成 OAuth 并返回 refresh token。Pixiv ID/密码可以留空，直接在弹出的 Pixiv 页面登录；这样可以处理验证码、Passkey 和 2FA。这个网页入口需要后端安装登录助手依赖：

```powershell
python -m pip install -e ".[pixiv-login]"
```

注意：可见浏览器窗口会出现在运行后端的机器上。本地自部署最适合这条路线；公网服务器如果没有桌面环境，管理员未必能看到窗口。对于公网图床，只建议可信管理员使用这个入口。如果不希望在网页里提交 Pixiv 密码，也可以在服务器或本机命令行获取 refresh token：

```powershell
nyagallery --storage storage pixiv-login-browser
```

如果 Pixiv 弹出验证码、Passkey 或 2FA，无头网页登录通常无法继续。此时请使用管理页的“启动可见 Pixiv 登录”，或使用上面的可见浏览器命令完成挑战，然后把输出的 refresh token 粘贴回管理页。

只输出 refresh token，方便复制到环境变量：

```powershell
nyagallery --storage storage pixiv-login-browser --plain
```

无头模式只适合你明确想在本机命令行传入账号密码时使用：

```powershell
nyagallery --storage storage pixiv-login-browser --headless --username "your-pixiv-id" --password "your-password"
```

拿到 token 后，可以设置环境变量，也可以在管理页 Pixiv 配置里临时填入：

```powershell
$env:PIXIV_REFRESH_TOKEN = "your-refresh-token"
```

管理页的 `OAuth` 选项也是这条路线：可以直接点“网页获取 Refresh Token”，也可以运行 `pixiv-login-browser` 后把输出粘贴进去。`手动` 选项保留了 OAuth callback/code 换取入口，但 Pixiv 的网页跳转经常会卡在 `accounts.pixiv.net/post-redirect` 或跳到第三方 callback，所以只作为备用方案。Cookie 粘贴仍可作为临时获图备用通道。

外部浏览器扩展如果已经在用户授权下拿到了 Pixiv 会话 Cookie，可以调用后端 Cookie OAuth 交换接口。这个接口不是把 Cookie 直接变成 token，而是把 Cookie 注入临时浏览器上下文完成 Pixiv OAuth 跳转，再用 callback code 换取 refresh token：

```http
POST /api/sync/pixiv/session/exchange
Authorization: Bearer your-nya-api-token
Content-Type: application/json

{
  "cookie": "PHPSESSID=...; device_token=...",
  "label": "extension",
  "save": true,
  "return_token": true
}
```

短别名：`POST /api/pixiv/session/exchange`。`save=true` 时 token 会保存到当前 NyaGallery 账号；管理员可以额外传 `username` 保存到指定账号。非管理员只能保存到自己账号。

Cookie 本身也可以在管理页像 Token 一样保存；`浏览器 Cookie` 右侧的“下载插件”会提供我们打包好的浏览器扩展，用来方便提取 Cookie。

公开 Pixiv 作品和公开用户作品不需要登录即可抓取，网页管理页默认使用“公开”模式；登录态主要留给收藏夹、关注、私有上下文等需要账号的来源。实际使用中登录态更容易触发 Pixiv 429 时，优先切回公开模式，或增加请求间隔。

选择 Token/Cookie/OAuth 模式时，管理页默认开启“优先公开抓取”：后端会先尝试公开抓取，公开接口不支持或失败时才使用已配置的 Token/Cookie。遇到 Pixiv 429 时不会切换到登录态重试，以免扩大风控风险。

纯前端 OAuth 平替目前不作为推荐方案：浏览器端无法稳定读取 Pixiv 跨域页面、无法可靠捕获 Pixiv App 风格回调，也不能绕过 Pixiv 的 post-redirect 行为。可跑通的路线是“前端触发、后端临时浏览器自动化”，或者直接使用本机 CLI。

注意：Pixiv refresh token 可能以 `-` 开头。如果要直接作为命令参数传入，必须使用等号形式，否则命令行解析器会把 token 当成新的选项：

```powershell
nyagallery --storage storage pixiv-sync-pid 123456 --refresh-token=-your-refresh-token --generate-cache --rebuild-db
```

更推荐使用环境变量或管理页输入框，避免 token 出现在命令历史里。

### 保存多个 Pixiv Token

管理页的 Pixiv 配置可以把当前 refresh token 保存到当前 NyaGallery 账号下，并填写备注，例如“主账号”“R18 可见”“备用”。一个账号可以保存多个 Pixiv token；列表只显示前缀、后缀、备注、Pixiv 账号摘要、最后使用时间和来源 IP，不会在接口里回显完整 refresh token。

抓取时可以直接选择已保存的 token。选择保存项后，请求体只会发送 `pixiv_token_id`，后端会从数据库取出 refresh token 并记录最后使用时间/IP。也可以不选择保存项，继续使用临时粘贴的 token 或环境变量 `PIXIV_REFRESH_TOKEN`。

注意：Pixiv refresh token 必须能被后端取出使用，因此目前会作为敏感凭据保存在数据库中，而不是像 API Token 那样只保存哈希。请把 `storage/nyagallery.db`、PostgreSQL 备份、服务器账号权限都当作敏感资产管理；如果 token 泄露，请重新登录 Pixiv 生成新 token，并撤销旧保存项。

### Token 有效期

Pixiv OAuth 返回的 `expires_in` 通常是 `3600`，这指的是 access token 大约 1 小时有效；NyaGallery 和 `pixivpy3` 使用的是 refresh token，会在需要时换取新的 access token。refresh token 没有一个公开保证的固定有效期，通常可以长期使用，但在 Pixiv 改密、撤销登录、风控、应用策略变化或 token 泄露后可能失效。失效时重新走一次“启动可见 Pixiv 登录”并保存新的 token 即可。

### Linux 部署与可见浏览器

前后端搬到 Linux 后，普通 API、上传、搜索、转码逻辑不变；主要差异在 Pixiv 可见浏览器会打开在“运行后端的 Linux 机器”上。

有桌面环境的 Linux：

```bash
python -m pip install -e ".[dev,media,pixiv,pixiv-login]"
python -m playwright install chromium
nyagallery --storage storage serve --host 0.0.0.0 --port 8001
```

然后启动前端：

```bash
cd frontend
npm install
NYA_API_BACKEND=http://127.0.0.1:8001 npm run dev -- -H 0.0.0.0 -p 3000
```

无桌面服务器有三种推荐路线：

- 最稳：在自己的本地电脑运行 `nyagallery pixiv-login-browser --plain` 获取 refresh token，再粘贴到服务器管理页并保存。
- 远程可交互：给服务器配置 VNC/noVNC 或 SSH X11 转发，让“启动可见 Pixiv 登录”弹出的浏览器能被管理员看到并操作。
- 仅自动化：使用 `xvfb-run` 可以让 Playwright 在无显示环境运行，但遇到验证码、Passkey、2FA 时你看不到页面，因此不适合作为主要登录路线。

示例：

```bash
sudo apt install xvfb
xvfb-run -a nyagallery --storage storage serve --host 0.0.0.0 --port 8001
```

生产部署建议用 `systemd` 分别管理后端和前端，并把 `NYA_API_BACKEND`、`NYAGALLERY_STORAGE`、`NYAGALLERY_DATABASE_URL` 写进服务环境变量。前端只负责反向代理 `/api/*` 到后端；如果通过公网访问，请再放一层 nginx/Caddy 做 HTTPS、静态缓存和真实 IP 传递。

同步单个作品 PID：

```powershell
nyagallery --storage storage pixiv-sync-pid 123456 --generate-cache --rebuild-db
```

同步某个作者 UID 的作品：

```powershell
nyagallery --storage storage pixiv-sync-user 88888 --limit 50 --generate-cache --rebuild-db
```

同步会做这些事：

- 下载 Pixiv 原始文件到 `storage/original/`
- 写入对应创作者的 `storage/metadata/{creator_key}.json`
- 保留 Pixiv 原始标签到 `pixiv_tags`
- 计算 SHA256
- 检测重复文件
- 可选生成 AVIF/Animated WebP 缓存
- 可选重建数据库索引

## 9. 上传本地图片

方式一：使用前端上传页。

```text
http://localhost:3000/upload
```

方式二：通过 API 上传。PowerShell 7 示例：

```powershell
$token = "your-api-token"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/upload" `
  -Method Post `
  -Headers @{ Authorization = "Bearer $token" } `
  -Form @{
    file = Get-Item "D:\Pictures\example.png"
    title = "example"
    generate_cache = "true"
  }
```

上传资源的 `source` 会记录为 `upload`，同样遵守“原始文件不可覆盖”和“metadata 可重建”的原则。
下载原图时，归档文件仍然使用 `asset_key`，浏览器保存的文件名会使用上传时的文件名。
上传资源会写入 `uploader_user_id` 和 `uploader_username`。如果上传时没有填写作者，metadata 会归入 `storage/metadata/user_{id}.json`。

## 10. 搜索与标签语法

支持 AND 查询：

```text
character:misaka_mikoto series:toaru
```

多页 Pixiv 作品（例如漫画）在数据库里仍然会按“每张图片一个 asset”保存，方便单页转码、去重和删除；前端首页和“所有文件”默认会按 `source + source_id` 折叠为一个作品卡片，并用 `12P` 这类标记显示页数。关闭“折叠多页”开关后会平铺所有图片，点击任意页会跳转到同一个作品详情页内的对应图片锚点。

作品详情页会把同一来源 ID 的所有图片纵向展示，并在右侧提供页目录，适合漫画、多图插画等场景快速跳转。

支持排除标签：

```text
character:misaka_mikoto -rating:r18
```

支持别名解析：

```text
御坂美琴
Misaka Mikoto
misaka_mikoto
```

支持原始文件名搜索：

```text
filename:2026-04-22
original_filename:"2026-04-22 储君可丽希亚"
储君可丽希亚
-filename:草稿
```

普通词如果没有解析成标签，会作为 `original_filename` 片段搜索；文件名里有空格时可以用引号。

隐藏标签不会主动出现在前台浏览和标签列表里：

```text
hide
/hide-spoiler
/hide-client-a
```

`hide` 会保存为 `meta:hide`，`/hide-xxx` 会保存为 `meta:hide_xxx`。默认搜索、随机图和首页/所有文件浏览会排除所有隐藏标签族；显式搜索 `hide` 或某个 `/hide-xxx` 才会返回对应资源。管理页 `/admin?section=tags` 仍可搜索这些标签，便于维护别名和统计。

支持自动比例标签：

```text
meta:landscape
meta:portrait
meta:square
meta:aspect_16_9
meta:aspect_9_16
meta:aspect_1_1
meta:unusual_aspect
meta:landscape_wallpaper
meta:portrait_wallpaper
```

默认标签目录也支持部分中文别名，例如 `横屏`、`竖屏`、`方形`、`异形比例`、`横屏壁纸推荐`、`竖屏壁纸推荐`。

支持来源与日期派生标签：

```text
source:pixiv
source:upload
date:2026
date:2026_05
date:2026_05_20
type:illustration
type:manga
type:ugoira
rating:safe
rating:r18
meta:ai_generated
```

来源站点的原始标签也会进入 `source_tag:*`。Pixiv 抓取结果如果带有 `pixiv_tag_details`，会优先用翻译名生成规范标签，例如 `{"name":"猫","translated_name":"cat"}` 会索引为 `source_tag:cat`，同时把 `猫` 作为别名；没有翻译时会直接用原文生成 `source_tag:*`。因此可以搜索：

```text
猫
source_tag:cat
school uniform
```

这类标签和人工维护的 `character:`、`series:`、`general:` 分开管理；如果某个原文已经是标准标签别名，标准标签仍然保留，来源标签也会以 `source_tag:*` 形式进入索引。

详情页的“来源标签”胶囊可以直接点击，会跳转到对应 `source_tag:*` 筛选结果。

标签显示名由后端 `storage/tags/catalog.json` 统一维护，可在每个标签上配置 `labels`，例如：

```json
{
  "name": "character:misaka_mikoto",
  "labels": {
    "zh-CN": "御坂美琴",
    "en-US": "Misaka Mikoto"
  }
}
```

前端语言切换只负责选择 `labels` 中的显示名；标签翻译不写进前端 `lang/*.json`。这样多个前端、多个后端实例或云存储同步时，都以同一份 tag catalog 为准。也可以通过 `PUT /api/tags/{tag}/labels` 更新显示名。

Pixiv 同步会优先使用 Pixiv 的 `create_date`；本地上传如果文件名类似 `2026-04-22_ 标题_143856839_p0.png`，会自动解析出作品日期、标题、Pixiv 作品 ID 和页码。作品 ID 与页码会放入 `extra`，不会作为高基数 tag 塞进标签云。

搜索接口支持排序：

```text
GET /api/search?sort=artwork_date&order=desc
GET /api/search?sort=uploaded_at&order=desc
GET /api/search?sort=original_filename&order=asc
```

可用排序字段：`artwork_date`、`uploaded_at`、`pixiv_upload_date`、`original_filename`、`title`、`artist`、`source_id`、`asset_key`。

API 示例：

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/api/search?q=character:misaka_mikoto%20-rating:r18"
```

前端搜索框也使用同一套语法。

## 11. 编辑标签

推荐在前端详情页编辑标准标签：

```text
http://localhost:3000/asset/{asset_key}
```

也可以调用 API：

```powershell
$token = "your-api-token"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/assets/123456/tags" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body '{"canonical_tags":["character:misaka_mikoto","series:toaru"]}'
```

注意：

- `pixiv_tags` 是来源站点原始标签，不要修改。
- `canonical_tags` 是用户维护的标准标签，会写回 metadata。
- `source_tag:*` 是从来源标签细节自动索引出来的可搜索标签，不需要手工写进 `canonical_tags`。
- 标签别名、蕴含、自动比例标签和壁纸推荐标签在重建索引时计算。

## 12. 生成或重建媒体缓存

为全部资源生成缓存：

```powershell
nyagallery --storage storage generate-cache
```

生成缓存并重建数据库：

```powershell
nyagallery --storage storage rebuild-db --generate-cache
```

通过 API 生成：

```powershell
$token = "your-api-token"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/media/generate" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body '{"asset_key":null}'
```

静态图片缓存：

```text
storage/preview/{asset_key}.avif
storage/thumbs/{asset_key}.avif
```

Pixiv ugoira 缓存：

```text
storage/preview/{asset_key}.webp
storage/thumbs/{asset_key}.avif
```

缓存文件不是资产，可以删除后重新生成。

## 13. 日常维护流程

同步新 Pixiv 作品：

```powershell
$env:PIXIV_REFRESH_TOKEN = "your-refresh-token"
nyagallery --storage storage pixiv-sync-pid 123456 --generate-cache --rebuild-db
```

手动修改 `storage/tags/catalog.json` 后：

```powershell
nyagallery --storage storage rebuild-db
```

删除预览缓存后：

```powershell
nyagallery --storage storage generate-cache
nyagallery --storage storage rebuild-db
```

数据库损坏或迁移后：

```powershell
Remove-Item storage\nyagallery.db
nyagallery --storage storage rebuild-db
```

只要 `storage/original/` 和 `storage/metadata/` 还在，图库资产就可以恢复。

## 14. 删除与清理

删除分两步：

1. 非管理员或管理员发起删除请求，只标记资源为待清理。
2. 管理员确认后调用清理请求，才会彻底删除文件。

标记待清理：

```powershell
$token = "editor-or-admin-token"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/assets/upload_xxx" `
  -Method Delete `
  -Headers @{ Authorization = "Bearer $token" }
```

这一步会在 metadata 中写入：

```json
{
  "deletion_status": "pending_cleanup",
  "deleted_at": "2026-06-07T12:00:00Z",
  "deleted_by_user_id": 1,
  "deleted_by_username": "editor"
}
```

待清理资源会从普通搜索、详情页和随机图接口中隐藏，但原图和 metadata 仍然保留。

管理员彻底清理：

```powershell
$token = "admin-token"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/assets/upload_xxx/cleanup" `
  -Method Delete `
  -Headers @{ Authorization = "Bearer $token" }
```

彻底清理会删除：

```text
storage/original/{asset_key}.*
storage/preview/{asset_key}.*
storage/thumbs/{asset_key}.*
metadata 中对应 assets 条目
数据库中的资产与标签索引
```

## 15. 常用 API

公开读取：

```text
GET /health
GET /api/site/config
GET /api/search?q=...&sort=artwork_date&order=desc
GET /api/img/random
GET /api/img/{tag}
GET /api/assets/{asset_key}
GET /api/assets/{asset_key}/siblings
GET /api/assets/{asset_key}/preview
GET /api/assets/{asset_key}/thumb
GET /api/tags/suggest?q=...
GET /api/tags/catalog
GET /api/tags/summary
```

需要权限：

```text
GET  /api/assets/{asset_key}/original
POST /api/upload
POST /api/assets/{asset_key}/tags
POST /api/media/generate
POST /api/rebuild
GET  /api/uploads/history
GET  /api/uploads/logs
GET  /api/transcode/jobs
POST /api/transcode/assets/{asset_key}/start
GET  /api/security/settings
PUT  /api/security/settings
GET  /api/security/access-logs
POST /api/sync/pixiv/{pid}
POST /api/sync/pixiv/user/{uid}
POST /api/sync/pixiv/session/exchange
POST /api/users
GET  /api/users
POST /api/users/{username}/password
POST /api/users/{username}/token
GET  /api/users/{username}/tokens
DELETE /api/tokens/{token_id}
DELETE /api/assets/{asset_key}
DELETE /api/assets/{asset_key}/cleanup
```

带 Token 请求：

请求头统一写法：

```http
Authorization: Bearer your-api-token
```

JSON 请求需要额外带：

```http
Content-Type: application/json
```

PowerShell 推荐先保存基础地址和 Token：

```powershell
$base = "http://127.0.0.1:8001"
$token = "your-api-token"
$headers = @{ Authorization = "Bearer $token" }
```

查询公开接口不一定需要 Token，但带上也可以：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/search?q=character:misaka_mikoto%20-rating:r18&limit=20&sort=artwork_date&order=desc" `
  -Headers $headers
```

下载原图需要 `viewer` 及以上权限：

```powershell
Invoke-WebRequest `
  -Uri "$base/api/assets/upload_xxx/original" `
  -Headers $headers `
  -OutFile ".\original.bin"
```

更新资源标签，适合给图片加普通标签、R18/AI 标签或隐藏标签：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/assets/upload_xxx/tags" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body (@{
    canonical_tags = @("character:misaka_mikoto", "rating:safe", "/hide-spoiler")
  } | ConvertTo-Json)
```

上传文件使用 `multipart/form-data`，不要手动设置 `Content-Type`。下面的 `-Form` 写法需要 PowerShell 7；PowerShell 5.1 可以改用下方 curl 或 Python 示例：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/upload" `
  -Method Post `
  -Headers $headers `
  -Form @{
    file = Get-Item ".\sample.png"
    title = "sample"
    artist_name = "artist name"
    generate_cache = "false"
  }
```

触发缓存生成：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/media/generate" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body '{"asset_key":"upload_xxx"}'
```

重建数据库索引：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/rebuild" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body '{"generate_cache":false}'
```

同步单个 Pixiv 作品：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/sync/pixiv/123456789" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body (@{
    auth_mode = "public"
    public_first = $true
    rebuild_db = $true
    generate_cache = $true
    request_delay_seconds = 1
    concurrency = 1
  } | ConvertTo-Json)
```

签发新的 API Token：

```powershell
Invoke-RestMethod `
  -Uri "$base/api/users/admin/token" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body '{"label":"script on workstation"}'
```

curl 写法：

```bash
BASE=http://127.0.0.1:8001
TOKEN=your-api-token

curl -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/search?q=meta:landscape&limit=10"

curl -X POST "$BASE/api/assets/upload_xxx/tags" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"canonical_tags":["rating:safe","/hide-spoiler"]}'

curl -X POST "$BASE/api/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample.png" \
  -F "title=sample" \
  -F "generate_cache=false"
```

Python `requests` 写法：

```python
import requests

base = "http://127.0.0.1:8001"
token = "your-api-token"
headers = {"Authorization": f"Bearer {token}"}

items = requests.get(
    f"{base}/api/search",
    headers=headers,
    params={"q": "meta:landscape", "limit": 10},
).json()["items"]

with open("sample.png", "rb") as file:
    asset = requests.post(
        f"{base}/api/upload",
        headers=headers,
        files={"file": ("sample.png", file, "image/png")},
        data={"title": "sample", "generate_cache": "false"},
    ).json()

requests.post(
    f"{base}/api/assets/{asset['asset_key']}/tags",
    headers=headers,
    json={"canonical_tags": ["rating:safe", "/hide-spoiler"]},
).raise_for_status()
```

常见响应字段：

```text
/api/search                         -> { items, limit, offset, sort, order }
/api/site/config                    -> { project_homepage, repository, icp_beian }
/api/assets/{asset_key}             -> 单个资产 JSON，含 tags/canonical_tags/preview_url/thumb_url
/api/upload                         -> 上传后的资产 JSON
/api/uploads/history                -> { items, limit, offset }
/api/transcode/jobs                 -> { items, limit, offset }
/api/users/{username}/token         -> { token }
```

## 16. 测试

运行后端测试：

```powershell
python -m pip install -e ".[dev,media]"
python -m pytest
```

前端类型检查和构建：

```powershell
cd frontend
npm run typecheck
npm run build
```

## 17. 常见问题

### 前端没有图片

先确认后端有资源：

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/api/search?limit=1"
```

如果为空，先同步或上传资源，然后执行：

```powershell
nyagallery --storage storage rebuild-db
```

### 预览图打不开

原图会作为预览回退，但推荐生成缓存：

```powershell
nyagallery --storage storage generate-cache
nyagallery --storage storage rebuild-db
```

### 管理接口返回 401

确认网页端已经登录具有对应权限的账号，或在脚本/API 请求中带上：

```text
Authorization: Bearer your-api-token
```

### Pixiv 同步失败

确认已安装 Pixiv 可选依赖并设置 refresh token：

```powershell
python -m pip install -e ".[pixiv]"
$env:PIXIV_REFRESH_TOKEN = "your-refresh-token"
```

如果没有 refresh token，先用本地浏览器助手获取：

```powershell
python -m pip install -e ".[pixiv-login]"
nyagallery --storage storage pixiv-login-browser --plain
```

首次使用 Playwright 时会自动安装/调用 Chromium，可能需要等待一会儿。若网络或代理导致浏览器打不开，先设置 `HTTPS_PROXY` 或 `ALL_PROXY` 后重试；遇到 Pixiv 429 时降低并发、加大请求间隔，等限流窗口过去再继续。

### 不小心删了数据库

数据库可以重建：

```powershell
nyagallery --storage storage rebuild-db
```

### 删除后前端看不到图片

这是正常的。`DELETE /api/assets/{asset_key}` 只是把资源标记为 `pending_cleanup`，普通搜索和详情会隐藏它。

如果只是误删请求，可以在 metadata 中移除：

```json
"deletion_status": "pending_cleanup",
"deleted_at": "...",
"deleted_by_user_id": 1,
"deleted_by_username": "editor"
```

然后重建数据库：

```powershell
nyagallery --storage storage rebuild-db
```

如果已经调用 `/cleanup`，文件和 metadata 条目已经彻底删除，只能从备份恢复。

真正需要备份的是：

```text
storage/original/
storage/metadata/
storage/tags/
```

## 18. 备份建议

最小备份：

```text
storage/original/
storage/metadata/
storage/tags/catalog.json
```

可选备份：

```text
storage/nyagallery.db
storage/preview/
storage/thumbs/
```

`preview/` 和 `thumbs/` 是缓存，不备份也可以重建。
## 19. 安全、访问日志与限流

管理页 `/admin` 中新增了“安全与访问控制”区域，只有 `admin` 可以查看和编辑。这里可以调整：

- 是否启用安全策略
- 是否记录访问日志，以及日志保留条数
- 全局、单 IP、默认用户并发上限
- 单 IP、默认用户每分钟请求数
- 单 IP、默认用户每分钟请求体积
- 上传请求体积上限
- 按角色组（viewer/editor/admin）覆盖默认用户限额
- 按具体用户覆盖角色组或默认用户限额

viewer API 白名单、可信 Origin、代理 IP 头这类底层安全项不在前端展示，改用 CLI 调整：

```powershell
nyagallery --storage storage security-config

nyagallery --storage storage security-config `
  --csrf-origin-check on `
  --trust-proxy-headers off `
  --viewer-api-whitelist-enabled off `
  --trusted-origin "http://10.147.20.210:3000"
```

默认值偏宽松，正常看图、搜索、缩略图加载和日常上传一般不会碰到限制；异常的高并发、超高频请求或超大上传会被拒绝。被拒绝的请求会写入访问日志，状态码通常是：

```text
403  API 不在白名单内，或 CSRF Origin 检查失败
413  请求体超过上传上限
429  请求频率、流量或并发超过限制
```

管理 API：

```text
GET /api/security/settings
PUT /api/security/settings
GET /api/security/access-logs?limit=100&offset=0&q=rate
```

访问日志会自动跳过普通成功的轮询 GET，例如 `/api/uploads/history`、`/api/uploads/logs`、`/api/transcode/jobs`；被拒绝、报错、以及写操作仍会记录。用户和管理员的写操作会额外写入文件：

```text
storage/logs/operations.log
```

使用 `nyagallery serve` 启动时，uvicorn 的逐请求 access log 默认关闭；需要排查代理或路由问题时可以显式打开：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001 --access-log
```

示例：

```powershell
$token = "admin-api-token"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/security/settings" `
  -Headers @{ Authorization = "Bearer $token" }

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/security/settings" `
  -Method Put `
  -Headers @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body '{"role_limits":{"viewer":{"user_requests_per_minute":900}},"max_ip_concurrency":32}'
```

网页端现在使用 cookie 会话和 CSRF Token；`Authorization: Bearer <token>` 保留给脚本、外部程序和旧客户端使用。

## 20. Cookie 会话、账号密码与多 API Token

网页端登录已经改为账号密码机制：

```text
POST /api/auth/login
POST /api/auth/logout
POST /api/auth/password
GET  /api/me
```

登录成功后后端会写入两个 cookie：

```text
nya_session  HttpOnly 会话 cookie，前端 JavaScript 读不到
nya_csrf     CSRF token cookie，前端会在写请求里作为 X-CSRF-Token 发送
```

前端页面会自动处理 cookie 和 CSRF header。脚本或外部程序仍然可以继续使用 API Token：

```text
Authorization: Bearer nya_xxxxx
```

API Token 现在和账号绑定，并且一个账号可以拥有多个 Token。登录用户可以查看、签发和撤销自己的 Token；只有 `admin` 可以查看、签发或撤销其他账号的 Token。

接口：

```text
POST   /api/users/{username}/token        # 为账号新增一个 Token
GET    /api/users/{username}/tokens       # 查看该账号已有 Token
DELETE /api/tokens/{token_id}             # 撤销指定 Token
```

签发 Token 时可以传备注：

```json
{
  "label": "scripts"
}
```

旧版单 Token 字段仍保留兼容：已有旧 Token 不会立刻失效；新签发的 Token 会进入多 Token 表。

`GET /api/users/{username}/tokens` 会返回每个 Token 的最后使用时间 `last_used_at` 和最后来源 IP `last_used_ip`。网页端也会在管理页显示这两个字段。

重设自己的网页登录密码：

```json
{
  "old_password": "current-password",
  "new_password": "new-password"
}
```

## 21. 登录 Not Found 与重设密码

如果登录页提交后显示 `Not Found`，通常表示前端代理到的后端还不是带有 `/api/auth/login` 的新版后端，或者 `NYA_API_BACKEND` 指到了旧端口。处理顺序：

```powershell
# 1. 停掉旧后端，重新启动新版后端
nyagallery --storage storage serve --host 127.0.0.1 --port 8001

# 2. 如果前端 dev server 已经启动很久，也重启一次
cd frontend
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"
npm run dev
```

可以直接检查登录 API 是否存在：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/auth/login" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"username":"admin","password":"your-password"}'
```

如果忘记或不确定 admin 密码，可以直接重设：

```powershell
nyagallery --storage storage set-password admin --password new-secret
```

`setup --password` 现在对已存在用户也会更新密码：

```powershell
nyagallery --storage storage setup --username admin --role admin --password new-secret
```
