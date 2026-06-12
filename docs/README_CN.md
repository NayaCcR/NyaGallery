# NyaGallery 首页

[English home](../README.md)

NyaGallery 是一个面向插画收藏的自部署图库系统，用于归档、浏览、搜索、打标签、上传和同步图片资源。当前包含 FastAPI 后端、Next.js 前端、不可变原图存储、可重建 metadata/数据库索引、Pixiv 同步、多用户权限、API Token、媒体缓存，以及可选 PostgreSQL/Redis 支持。

## 项目特色

- 归档优先：原图按不可变记录保存，metadata、媒体缓存和数据库索引都可以重建。
- 面向插画工作流：Pixiv 同步、多页作品、ugoira 媒体缓存、来源标签、R-18/AI 内容偏好和隐藏标签族都是一等功能。
- 后端统一标签语义：别名、多语言显示名、蕴含关系、建议标签、来源站点标签和隐藏标签都由 tag catalog 管理，不散落在各个前端里。
- 自部署但预留扩展：本地可用 SQLite，后续规模变大时可选 PostgreSQL、Redis，并为多后端和云存储方向保留空间。
- 实用权限体系：角色、HttpOnly 会话、CSRF 防护、Bearer API Token、上传历史、访问日志、操作日志和 developer 专用配置工具都内置。
- 现代浏览体验：响应式瀑布流、侧边栏工作区、详情页、上传队列、搜索工具和模块化管理后台。

## 为什么做 NyaGallery

NyaGallery 的位置介于下载脚本、普通文件浏览器和完整 booru 图站系统之间。

- 相比文件夹或普通相册，它会保留来源 metadata，支持结构化标签，并能从归档文件重建索引。
- 相比一次性下载脚本，它给下载后的收藏一个长期工作台：浏览、搜索、改标签、上传、审计和重建缓存都在同一个界面里。
- 相比通用图库/DAM，它更理解插画收藏里的 Pixiv ID、翻译来源标签、多页作品、ugoira、R-18/AI 过滤和 booru 风格标签关系。
- 相比偏公开图站的 booru 系统，它更偏个人或小团队私有归档：受控账号、私有存储、可重建 metadata 和管理维护能力是核心设计。

## 设计参考

- [Szurubooru](https://github.com/rr-/szurubooru)：NyaGallery 继承了 booru 系统里“标签应该结构化、可搜索、可维护”的核心思路。标准标签、分类、别名、蕴含、建议和查询解析都属于后端能力，而不是散落在前端里的显示文本。
- [ImageFlow](https://github.com/Yuri-NagaSaki/ImageFlow)：NyaGallery 保留了图片优先的浏览取向：快速扫图、瀑布流、轻量导航和预览驱动的交互。在这个基础上再补上原图归档完整性、可重建 metadata、来源标签、用户权限和管理维护能力。

## 文档导航

| 文档 | 作用 |
| --- | --- |
| [../README.md](../README.md) | 英文项目首页、快速上手和开发说明。 |
| [../READMORE.md](../READMORE.md) | 英文完整后端、存储、标签、Pixiv、API 与测试说明。 |
| [README_CN.md](README_CN.md) | 中文项目首页、快速上手和开发说明。 |
| [READMORE_CN.md](READMORE_CN.md) | 中文完整后端、存储、标签、Pixiv、API 与测试说明。 |
| [QUICKSTART_CN.md](QUICKSTART_CN.md) | 中文简洁部署步骤和常用命令。 |
| [USAGE_CN.md](USAGE_CN.md) | 中文完整使用手册、API 示例、维护流程和 FAQ。 |
| [summary.md](summary.md) | 中文当前实现、模块边界和后续方向总结。 |
| [../frontend/README.md](../frontend/README.md) | 前端结构、页面、hooks、API 对照和构建说明。 |
| [../config.example.toml](../config.example.toml) | 后端部署配置模板。 |

## 环境要求

- Python 3.11+
- Node.js 18+
- npm
- 可选：PostgreSQL、Redis、Pixiv refresh token、媒体/Pixiv 可选依赖

## 快速启动

安装后端：

```powershell
python -m pip install -e ".[media,pixiv,pixiv-login,postgres,redis]"
```

安装前端：

```powershell
cd frontend
npm install
cd ..
```

初始化 `storage/`、标签目录、数据库和管理员账号：

```powershell
nyagallery --storage storage setup --username admin --role admin --password 123123
```

启动后端：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

另开终端启动前端：

```powershell
cd frontend
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"
npm run dev
```

访问：

```text
http://localhost:3000
```

## 配置文件

需要可复用部署配置时，复制模板：

```powershell
Copy-Item config.example.toml nyagallery.toml
nyagallery --config nyagallery.toml serve
```

主要配置段：

- `[core]`：存储根目录、数据库 URL、标签目录路径
- `[server]`：监听地址、端口、访问日志、安全 Cookie
- `[site]`：项目主页、仓库地址、可选 ICP 备案号
- `[pixiv]`：可选 Pixiv 默认凭据和同步默认参数
- `[redis]`：可选 Redis URL 和共享安全限流
- `[developer]`：开发者专用配置编辑开关和白名单操作台开关

## 常用命令

重建数据库索引：

```powershell
nyagallery --storage storage rebuild-db
```

生成媒体缓存：

```powershell
nyagallery --storage storage generate-cache
```

同步单个 Pixiv 作品：

```powershell
nyagallery --storage storage pixiv-sync-pid 123456 --generate-cache --rebuild-db
```

创建用户：

```powershell
nyagallery --storage storage create-user viewer --role viewer --password 123123
```

创建可编辑配置和使用受控操作台的开发者账号。developer 账号只能通过本机 CLI 或已有 developer 用户创建：

```powershell
nyagallery --storage storage create-user dev --role developer --password 123123
```

签发 API Token：

```powershell
nyagallery --storage storage issue-token viewer
```

## 开发教程

后端检查：

```powershell
python -m py_compile src/nyagallery/*.py
python -m unittest tests.test_config tests.test_tags tests.test_db
```

前端检查：

```powershell
cd frontend
npm run typecheck
npm run lint
npm run build
```

推荐开发安装：

```powershell
python -m pip install -e ".[dev,media,pixiv,pixiv-login,postgres,redis]"
```

## 发行文件

建议包含：

- `src/`
- `frontend/`
- `pyproject.toml`
- `config.example.toml`
- `README.md`、`READMORE.md`、`docs/README_CN.md`、`docs/READMORE_CN.md`、`docs/QUICKSTART_CN.md`、`docs/USAGE_CN.md`、`docs/summary.md`、`frontend/README.md`
- `LICENSE`

不要包含运行时/缓存目录：

- `storage/`
- `frontend/node_modules/`
- `frontend/.next/`
- `frontend/tsconfig.tsbuildinfo`
- `dist/`、`build/`、`*.egg-info/`

## 架构说明

原图不可变；metadata、数据库索引和媒体缓存都可重建。标签别名、显示名、蕴含关系和来源站点标签由后端 tag catalog 统一管理，方便多个前端、多个后端实例或未来云存储部署共享同一套标签语义。
