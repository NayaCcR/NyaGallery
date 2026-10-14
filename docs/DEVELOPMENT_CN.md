# NyaGallery 开发指南

## 1. 代码布局

```text
src/nyagallery/        FastAPI、CLI、配置、存储、数据库、同步器
frontend/src/          Next.js 页面、hooks、组件和本地化
tests/                 后端单元/API/同步/媒体测试
config.example.toml    可复制的部署配置模板
docs/                  中文使用、部署、配置和 API 文档
```

后端的 `storage.py` 负责不可变原图和 metadata；`db.py` 负责索引和用户表；`tags.py` 负责标签目录及规范化；`media.py` 只生成可重建缓存；`app.py` 组合 API 和权限依赖。不要让前端自行推断标签语义或直接拼接本地文件路径。

## 2. 建立开发环境

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,media,pixiv,pixiv-login,postgres,redis]"
cd frontend
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
cd ..
nyagallery --storage storage setup --username developer --role developer
```

启动后端：

```bash
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

启动前端：

```bash
cd frontend
NYA_API_BACKEND=http://127.0.0.1:8001 pnpm run dev
```

Windows PowerShell 使用 `$env:NYA_API_BACKEND = "http://127.0.0.1:8001"`。Next.js 通过 rewrite 将 `/api/*` 和 `/health` 转发到后端；浏览器不应直接依赖后端端口。

## 3. 后端开发约定

- 新增持久化字段时，同时更新 SQLAlchemy 模型、metadata 读写、`rebuild-db` 和相关测试。
- 原图写入必须幂等且不可覆盖；缓存和数据库索引必须可以删除后重建。
- API 通过 FastAPI dependency 注入数据库会话和角色权限；不要在路由中复制密码或 Token 校验逻辑。
- 第三方来源实现请求限速、重试边界和 `--dry-run`（如适用），凭据通过配置/环境注入，不写入日志。
- 所有用户可见标签先经 `TagCatalog` canonicalize；来源原始标签保存在 metadata，不要覆盖。
- 写请求保持 CSRF 保护兼容；脚本访问使用 `Authorization: Bearer` API Token。

## 4. 前端开发约定

页面位于 `frontend/src/app`，可复用 UI 在 `components/ui`，后台业务面板在 `components/admin`，请求 hooks 在 `hooks`，类型集中在 `lib/types.ts`。新增文案同时修改 `src/lang/zh-CN.json` 和 `en-US.json`，使用 `useI18n().t(...)`，不要在组件里硬编码语言分支。

API 请求优先复用 `frontend/src/lib/api.ts`，让 cookie、CSRF 和错误格式保持一致。文件 URL 使用后端返回的资源链接，不能把服务器本地路径渲染到浏览器。

Pixiv PID 管理输入支持纯 ID、Pixiv artworks URL、`member_illust.php?illust_id=...` 和多项分隔输入；解析在前端完成，每个作品独立调用单 PID API，避免改变后端单任务语义。

上传页目录拖放通过 `webkitGetAsEntry` 递归展开目录，读取失败时对该条目跳过；普通文件继续使用 `DataTransfer.files` 回退，所有文件汇入同一去重和进度队列。

管理操作日志在客户端支持关键字搜索、状态过滤和 JSON 导出；搜索针对返回日志的序列化字段，导出只包含当前筛选结果。

服务端远程 URL 拉取集中于 `remote_upload.py`，仅允许无用户信息的 HTTP(S) URL。单次 DNS 结果中的每个地址都必须为全局可路由单播地址，IPv4 映射 IPv6 还要检查其 IPv4 地址；底层 socket 直接连接已验证的数值地址，不能校验后再按主机名解析。HTTPS 使用默认信任库和原域名 SNI/hostname 校验；不使用环境代理，不跟随任何重定向。端点通过线程池调用下载函数，并在复用上传链路后关闭内存文件流。下载限制为站点上限与 100 MiB 中的较小值，10 秒连接/读写超时和 30 秒总预算（含 DNS 等待），总时限通过关闭传输 socket 中断慢速响应。系统 DNS 调用本身无法取消；超时后守护解析线程可继续等待系统返回，但不会建立连接。响应 MIME 仅检查上游 `image/*` 声明，不能宣称完成内容解码验证。客户端只接收通用网络错误；测试使用模拟 DNS/socket/TLS，不真实抓取外网。

EXIF 提取集中于 `exif.py`，使用 Pillow `get_ifd` 解引用 EXIF/GPS 子目录，各字段独立校验；损坏 GPS 不应丢失设备和时间。上传队列传 `File.lastModified`，API 校验毫秒单位与范围后才写原图；远程上传显式传空来源时间。本地迁移读取源文件 mtime，保留已有 extra 和 artwork_date。`media.exif_timezone` 在配置读写和环境覆盖中保持一致；IANA 时区依赖系统数据库或可选安装的 tzdata，无数据库时可用固定偏移。

`tests/test_exif.py` 使用真实 JPEG EXIF 子目录，覆盖 offset 优先、默认时区、GPS 缺损、无 Pillow、原文件时间回退及配置往返。运行测试请设 `PYTHONPATH=src`，避免机器中其他 editable 安装被误导入；如默认临时目录不可写，使用工作区内独立 `--basetemp`，可加 `-p no:cacheprovider`。

## 5. 测试、检查和调试

```bash
python -m py_compile src/nyagallery/*.py
python -m pytest
cd frontend
pnpm run typecheck
pnpm run lint
pnpm run build
```

后端 API 测试应覆盖匿名、viewer/editor/admin/developer、Cookie+CSRF 和 Bearer Token；涉及文件的测试使用临时目录，不要写入仓库 `storage/`。同步器测试应使用 fixture 或 mock，避免在 CI 访问 Pixiv、X、Misskey 或 Fanbox。

常见诊断：

```bash
curl http://127.0.0.1:8001/health
nyagallery --storage storage rebuild-db
nyagallery --storage storage generate-cache
nyagallery --storage storage security-config
```

## 6. 提交前检查

- 新路由有权限依赖、参数范围和错误状态码。
- 新配置同时加入 dataclass、TOML 模板、环境变量覆盖和文档。
- 新文件格式有 MIME、大小和路径安全测试。
- 不提交 `storage/`、数据库、Token、Cookie、`.env`、`node_modules/`、`.next/`。
- 前后端构建和测试在干净虚拟环境中通过。
