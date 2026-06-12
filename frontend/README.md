# NyaGallery Frontend

NyaGallery 的 Next.js 前端，提供瀑布流浏览、标签筛选、上传、资产详情、Pixiv 同步和管理后台，对接同仓库的 FastAPI 后端。

Documentation: [project home](../README.md) | [full backend/API reference](../READMORE.md) | [中文首页](../docs/README_CN.md) | [中文完整说明](../docs/READMORE_CN.md) | [中文快速启动](../docs/QUICKSTART_CN.md) | [中文使用手册](../docs/USAGE_CN.md) | [实现总结](../docs/summary.md).

## 技术栈

- Next.js 14 App Router + TypeScript
- Tailwind CSS，自定义 shadcn 风格设计 token
- TanStack Query，用于搜索、资产详情、登录态和管理数据缓存
- 轻量本地化字典：`src/lang/*.json`
- 自研 UI primitives：Button、Input、Label、Badge、Skeleton、Spinner、TagChipInput、Toast 等
- Lucide 图标

## 目录

```text
frontend/
├─ src/
│  ├─ app/                                # App Router 路由
│  │  ├─ page.tsx                         # 首页：最新作品 / URL 搜索结果
│  │  ├─ files/page.tsx                   # 所有文件 / 排序浏览
│  │  ├─ search/page.tsx                  # 标签筛选、随机图、标签目录
│  │  ├─ asset/[key]/page.tsx             # 资产详情、多页作品、下载与标签编辑
│  │  ├─ upload/page.tsx                  # 批量上传
│  │  ├─ admin/page.tsx                   # 管理后台
│  │  ├─ login/page.tsx                   # 账号密码登录
│  │  ├─ faq/page.tsx                     # 说明与外部链接
│  │  └─ api/sync/pixiv/oauth/            # 长耗时 Pixiv 登录代理路由
│  ├─ components/
│  │  ├─ admin/                           # 管理页复用字段与面板组件
│  │  ├─ content/                         # 内容偏好筛选开关
│  │  ├─ gallery/                         # 瀑布流、无限滚动、资产卡片
│  │  ├─ layout/                          # AppShell / 主题 / 语言 / 用户菜单
│  │  ├─ providers/                       # QueryClient / Auth / Locale / Theme / Toast
│  │  └─ ui/                              # 基础 UI 组件
│  ├─ hooks/
│  │  ├─ admin/                           # 管理页状态、轮询与 API 操作 hooks
│  │  ├─ gallery/                         # 首页/瀑布流查询控制 hooks
│  │  ├─ search/                          # 搜索页标签选择与随机预览 hooks
│  │  └─ upload/                          # 上传队列与提交 hooks
│  ├─ lang/                               # 前端字典
│  └─ lib/                                # API client / types / utils
├─ public/                                # PWA manifest / 图标
└─ next.config.mjs                        # /api/* 与 /health 反代到后端
```

## 开发

```powershell
cd frontend
npm install

# 默认反代到 http://127.0.0.1:8001
npm run dev

# 自定义后端地址
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"; npm run dev
```

另开一个终端启动后端：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

打开前端终端显示的地址，通常是 <http://localhost:3000>。

## 当前页面

- `/`：最新作品瀑布流；支持 `/?q=character:misaka_mikoto -rating:r18` 搜索。
- `/files`：所有文件视图，可按作品日期、入库时间、Pixiv 修改时间、文件名、标题、作者、来源 ID 排序。
- `/search`：标签选择器、内容筛选、排除动图、随机图预览和跳转详情。
- `/asset/[key]`：详情页，支持多页作品浏览、原图下载、Pixiv 作品页跳转、API 链接、标签编辑、删除标记和管理员清理。
- `/upload`：批量上传图片或 zip，支持默认作者、默认标签、标签别名和上传后生成缓存。
- `/admin`：管理后台入口，按侧边栏二级模块进入仪表盘、Pixiv、上传与转码、安全、标签、维护、账户和开发者；模块入口会按当前角色隐藏。
- `/login`：账号密码登录，使用 HttpOnly cookie 会话。
- `/faq`：项目说明、致谢和个人链接。

## 设计约定

- 所有数据来自后端 `/api/*`，前端不直接访问 `storage/`。
- 开发环境通过 Next.js rewrites 转发 `/api/*` 和 `/health`，避免 CORS 并保留 cookie 会话。
- 匿名用户默认拥有 `view` 权限，可浏览首页、搜索、详情和缩略图；敏感内容由后端与内容偏好共同过滤。
- 登录后使用 HttpOnly cookie；Bearer Token 保留给脚本、外部程序和旧客户端。
- 详情页原图下载走 `/api/assets/{key}/original`，由后端流式返回原始字节。
- Pixiv 无头登录和可见浏览器登录通过 `src/app/api/sync/pixiv/oauth/*` 代理，避免 Next 默认请求超时影响长耗时登录。
- 全站使用 `components/layout/app-shell` 作为应用壳：桌面端左侧模块导航并在侧栏顶部承载主题/语言/账号，移动端使用顶部工具栏与横向导航；页脚位于内容区底部，左侧展示项目主页与 GitHub 仓库，中间按配置显示 ICP 备案号，右侧以说明型链接展示 ImageFlow 灵感和 Szurubooru 鸣谢。
- 页脚 ICP 备案号来自后端 `/api/site/config`；在后端 `nyagallery.toml` 的 `site.icp_beian` 留空时不显示，显示时链接到 `http://beian.miit.gov.cn`。

## 页面拆分现状

首页、搜索页和上传页已开始把可复用状态迁移到 `src/hooks/`：

- `hooks/gallery/use-gallery-query-controls`：首页 URL 查询、多选标签点击和多页折叠状态。
- `hooks/gallery/use-browse-gallery-queries`：首页和所有文件页的内容偏好查询组；无搜索词时以普通内容为基础，R-18/AI 开关只追加对应内容。
- `hooks/search/use-search-tags`：搜索页标签选择、分类/技术标签分组、排除动图和提交跳转。
- `hooks/search/use-random-preview`：随机图请求、Bearer Token 读取、Blob URL 生命周期和中止上一请求。
- `hooks/upload/use-upload-queue`：上传队列、文件去重、预览 URL 清理、默认元数据、标签别名解析和批量提交。
- `components/ui/switch-label`：首页和文件页共用的文字开关组件。

`/files` 页目前只包含少量排序与折叠状态，并复用浏览页内容偏好 hook；`/asset/[key]` 仍偏大，适合后续按“详情编辑 / 下载与 API 链接 / 资源展示”再拆。

`src/app/admin/page.tsx` 仍作为管理后台组合入口，但业务状态已开始迁移到 `src/hooks/admin/`：

- `use-admin-action`：统一按钮 busy 状态、成功提示和 API 错误提示。
- `use-admin-operations` / `use-admin-pixiv-logs`：上传、转码、Pixiv 日志轮询，包含页面隐藏暂停和活跃/空闲刷新节奏。
- `use-admin-tags`：标签别名列表、搜索过滤、保存和导出汇总。
- `use-admin-security`：安全设置、角色/用户限额、访问日志和用户列表同步。
- `use-admin-accounts`：用户、密码、API Token 的表单状态和操作。
- `use-admin-developer`：developer 专用配置草稿、后端节点状态和白名单维护动作。
- `use-admin-pixiv-settings` / `use-admin-pixiv-credentials`：Pixiv 后端能力、同步参数、已保存 Token/Cookie 凭据和最近登录用户信息。
- `use-admin-pixiv-oauth`：Pixiv OAuth 手动回调、无头登录、可见浏览器登录轮询和 post-redirect URL 识别。

`src/components/admin/` 已承接一部分管理页 UI：

- `admin-fields`：开关、数字输入、文本域、限额网格、空状态。
- `admin-pixiv-panel`：Pixiv 配置、OAuth/Token/Cookie 凭据入口、同步参数和抓取日志侧栏。
- `admin-security-panel`：安全策略、默认/角色/用户限额和访问日志查询面板。
- `admin-maintenance-panel` / `admin-tags-panel`：数据库重建、媒体缓存生成、标签别名搜索/保存和汇总导出。
- `admin-accounts-panel`：创建用户、API Token 签发/撤销、当前用户改密和管理员重置密码。
- `admin-developer-panel`：developer 专用配置编辑、后端节点状态和白名单维护动作。
- `admin-operations-panel`：上传与转码总面板，组合轮询状态、刷新入口、转码任务、上传历史和最近日志。
- `admin-operation-rows`：转码任务、上传历史、上传日志、Pixiv 日志、访问日志、API Token 列表。
- `pixiv-credential-managers`：Pixiv Token/Cookie 保存项选择、备注和撤销。
- `admin-format`：管理页日期、大小、状态、缓存、转码阶段等展示格式化工具。

`/admin` 已按“仪表盘 / Pixiv / 上传与转码 / 安全 / 标签 / 维护 / 账户 / 开发者”切成侧边栏二级模块，并通过 `lib/admin-sections` 统一维护角色可见性：
- `viewer`：仪表盘、上传与转码、账户。
- `editor`：仪表盘、Pixiv、上传与转码、账户。
- `admin`：全部管理模块。
- `developer`：admin 的超集，额外显示开发者模块。

页面内容也按当前 `section` 单模块挂载，隐藏的模块不会仅靠 CSS 收起；直接访问不可见 `section` 时会回落到该角色的默认可访问模块。

## 本地化

前端字典在 `src/lang/*.json`。新增语言时：

1. 复制 `src/lang/en-US.json` 或 `src/lang/zh-CN.json`。
2. 翻译 JSON 值，保持 key 不变。
3. 在 `src/lang/index.ts` 导入并加入 `dictionaries` 与 `localeOptions`。

站点导航、登录入口、主题切换、管理页轮询/日志/转码状态等已接入字典；部分页面仍保留直接中文文案，可继续逐步迁移到 `useI18n().t(...)`。

## 主要功能

- 响应式瀑布流，按图片比例占位，减少布局跳动。
- 无限滚动，使用 `IntersectionObserver` 预取下一页。
- 多标签 AND 搜索与 `-tag` 排除语法，搜索状态同步到 URL。
- 内容偏好开关：首页和所有文件页把敏感内容、AI 生成内容视为可追加内容；关闭时隐藏对应内容，打开时在普通内容基础上追加，不会把普通内容当作筛选结果排除。搜索页仍使用多标签 AND 与 `-tag` 排除语法。
- 隐藏标签族：`meta:hide`、`meta:hide_xxx` 和 `/hide-xxx` 输入形式不会主动展示在前台卡片、详情标签和搜索标签目录中；管理页标签模块保留完整列表和搜索。
- 来源标签：Pixiv 抓取的原始标签会索引为 `source_tag:*`，有翻译时优先用翻译名作为规范名、原文作为别名；详情页来源标签可点击跳转到对应筛选结果，该分类为后续接入其他来源平台预留。
- 标签显示名：前端不在 `lang/*.json` 里维护标签翻译，而是根据当前语言读取后端 tag catalog / asset `tag_details` 返回的 `labels`。
- 搜索页标签目录按分类聚合，技术标签默认折叠。
- 随机图支持叠加当前标签筛选，并可跳转到对应资产详情。
- 详情页支持多页 Pixiv 作品、原图下载、来源跳转、Pixiv 作品页跳转、标签编辑、Pixiv 原始标签、SHA256 和 API 链接复制/打开。
- 上传页支持批量队列、拖拽、默认元数据、标签别名和上传后缓存生成。
- 管理页支持按权限组拆分的 Pixiv 同步、上传与转码、访问日志、标签、维护、用户与 Token、安全限流配置，以及 developer 角色专用的可视化后端配置编辑和白名单开发者操作台。
- 深浅色主题切换，预渲染前注入主题脚本避免闪烁。
- PWA manifest 保留，可添加到主屏；当前未启用 Service Worker 离线缓存。

## 后端 API 对照

| 端点 | 当前前端使用位置 |
| --- | --- |
| `GET /health` | 手动健康检查；Next rewrite 保留 |
| `GET /api/site/config` | 页脚项目链接与可选 ICP 备案号 |
| `GET /api/me` | 登录态、权限、CSRF token |
| `POST /api/auth/login` `POST /api/auth/logout` `POST /api/auth/password` | 登录、退出、修改密码 |
| `GET /api/search` | 首页、所有文件、瀑布流分页 |
| `GET /api/img/random` | 搜索页随机图 |
| `GET /api/assets/{key}` | 详情页 |
| `GET /api/assets/{key}/siblings` | 详情页多页作品 |
| `GET /api/assets/{key}/preview` `GET /api/assets/{key}/thumb` | 卡片、详情页和 API 链接 |
| `GET /api/assets/{key}/original` | 原图下载和 API 链接 |
| `POST /api/assets/{key}/tags` | 详情页标签编辑 |
| `DELETE /api/assets/{key}` `DELETE /api/assets/{key}/cleanup` | 删除标记与管理员清理 |
| `GET /api/tags/summary` `POST /api/tags/summary/export` | 搜索页标签目录、管理页标签统计导出 |
| `PUT /api/tags/{tag}/aliases` `PUT /api/tags/{tag}/labels` | 管理页/外部工具维护标签别名和多语言显示名 |
| `POST /api/upload` | 上传页 |
| `POST /api/rebuild` `POST /api/media/generate` | 管理页数据库重建和缓存生成 |
| `GET /api/uploads/history` `GET /api/uploads/logs` | 管理页上传历史和日志 |
| `GET /api/transcode/jobs` `POST /api/transcode/assets/{key}/start` | 管理页转码队列与单项转码 |
| `GET /api/security/settings` `PUT /api/security/settings` `GET /api/security/access-logs` | 管理页安全配置与访问日志 |
| `GET/PUT /api/developer/config` `GET /api/developer/console` `POST /api/developer/console/reset-password` | 管理页开发者配置编辑和白名单操作台 |
| `GET /api/sync/pixiv/config` | 管理页 Pixiv 能力检测 |
| `POST /api/sync/pixiv/oauth/start` `POST /api/sync/pixiv/oauth/exchange` | 管理页手动 OAuth |
| `POST /api/sync/pixiv/oauth/browser-login` | 管理页无头 Pixiv 登录 |
| `POST /api/sync/pixiv/oauth/visible/start` `GET /api/sync/pixiv/oauth/visible/{sessionId}` | 管理页可见浏览器 Pixiv 登录 |
| `POST /api/sync/pixiv/{pid}` `POST /api/sync/pixiv/user/{uid}` | 管理页 Pixiv 单作品/用户同步 |
| `GET/POST /api/users...` `DELETE /api/tokens/{id}` | 管理页用户与 API Token |
| `GET/POST/PATCH/DELETE /api/users...pixiv-*` | 管理页 Pixiv Token/Cookie 凭据管理 |

`GET /api/tags/suggest` 和 `GET /api/tags/catalog` 仍在前端 API client 中保留，但当前页面主要使用 `GET /api/tags/summary` 来驱动标签目录。

## 构建

```powershell
npm run typecheck
npm run lint
npm run build
npm run start
```

生产环境同样需要让 `NYA_API_BACKEND` 指向真实后端，或在外层反向代理中把 `/api/*` 和 `/health` 转发到 FastAPI。
