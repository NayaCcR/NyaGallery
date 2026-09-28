# NyaGallery 简洁部署与常用命令

本文只记录安装流程和常用命令。以下命令默认在项目根目录执行。

文档导航：[中文首页](README_CN.md) | [中文完整说明](READMORE_CN.md) | [使用手册](USAGE_CN.md) | [实现总结](summary.md) | [前端说明](../frontend/README.md) | [英文首页](../README.md)。

## 1. 准备环境

- Python 3.11+，建议使用 conda/venv。
- Node.js 22.13+。
- pnpm 11.13.1（通过 Corepack）。
- 可选：需要 Pixiv 可见浏览器登录时，安装浏览器环境。

```powershell
conda create -n nyagallery python=3.11
conda activate nyagallery
```

## 2. 安装后端

推荐完整安装，包含媒体缓存、Pixiv 抓取和 Pixiv 浏览器登录：

```powershell
python -m pip install -e ".[media,pixiv,pixiv-login]"
```

如果要跑测试或开发：

```powershell
python -m pip install -e ".[dev,media,pixiv,pixiv-login]"
```

确认命令可用：

```powershell
nyagallery --help
```

## 3. 安装前端

```powershell
cd frontend
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
cd ..
```

## 4. 初始化

创建 `storage/`、标签库、数据库、管理员账号：

```powershell
nyagallery --storage storage setup --username admin --role admin --password 123123
```

如果没有写 `--password`，命令会交互式要求输入并确认密码。

## 5. 启动开发环境

后端：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001
```

前端：

```powershell
cd frontend
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"
pnpm run dev
```

访问：

```text
http://localhost:3000
```

局域网访问时，后端和前端都监听 `0.0.0.0`：

```powershell
nyagallery --storage storage serve --host 0.0.0.0 --port 8001
```

```powershell
cd frontend
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"
pnpm run dev -- -H 0.0.0.0 -p 3000
```

## 6. 生产启动

后端：

```powershell
nyagallery --storage storage serve --host 0.0.0.0 --port 8001
```

前端构建并启动：

```powershell
cd frontend
$env:NYA_API_BACKEND = "http://127.0.0.1:8001"
pnpm run build
pnpm run start -- -H 0.0.0.0 -p 3000
```

## 7. 常用命令

重建数据库索引：

```powershell
nyagallery --storage storage rebuild-db
```

重建数据库并生成缓存：

```powershell
nyagallery --storage storage rebuild-db --generate-cache
```

只生成预览/缩略图缓存：

```powershell
nyagallery --storage storage generate-cache
```

迁移旧 metadata 到按创作者分组的大 JSON：

```powershell
nyagallery --storage storage migrate-metadata
```

创建用户：

```powershell
nyagallery --storage storage create-user viewer --role viewer --password 123123
```

重设密码：

```powershell
nyagallery --storage storage set-password admin --password 123123
```

签发 API Token：

```powershell
nyagallery --storage storage issue-token admin --label main
```

查看安全配置：

```powershell
nyagallery --storage storage security-config
```

添加可信 Origin：

```powershell
nyagallery --storage storage security-config --trusted-origin "http://localhost:3000"
```

打开后端 access log：

```powershell
nyagallery --storage storage serve --host 127.0.0.1 --port 8001 --access-log
```

## 8. Pixiv 常用命令

公开作品和公开用户作品默认不需要登录，推荐优先使用公开模式：

```powershell
nyagallery --storage storage pixiv-sync-pid 123456 --generate-cache --rebuild-db
nyagallery --storage storage pixiv-sync-user 88888 --limit 50 --generate-cache --rebuild-db
```

登录态只建议用于收藏夹、关注、私有上下文等需要账号的来源。登录后更容易遇到 Pixiv 429 时，请降低并发并增加请求间隔。

管理页默认开启“优先公开抓取”：选择 Token/Cookie 时会先试公开接口，公开失败后才使用登录态；429 不会触发登录态重试。

本地浏览器获取 Refresh Token：

```powershell
nyagallery --storage storage pixiv-login-browser --plain
```

无图形 Linux 推荐做法：在自己的 Windows/macOS/Linux 桌面电脑运行上面的命令获取 Refresh Token，再粘贴到服务器管理页保存。服务器不需要图形界面，也不要在服务器上输入 Pixiv 密码。

浏览器扩展也可以在用户授权后把 Pixiv Cookie 交给后端换取并保存 Refresh Token：

```http
POST /api/sync/pixiv/session/exchange
Authorization: Bearer your-nya-api-token

{"cookie":"PHPSESSID=...; device_token=...","label":"extension","save":true}
```

管理页的 `浏览器 Cookie` 区域也可以直接保存 Cookie；右侧“下载插件”链接会下载本项目提供的浏览器扩展 zip。

如果只有服务器命令行，也可以使用手动 OAuth 备用通道。服务器生成登录 URL：

```powershell
nyagallery --storage storage pixiv-oauth-start
```

把输出里的 `authorization_url` 复制到本地浏览器打开，完成 Pixiv 登录、验证码或 2FA。登录结束后复制最终 callback URL，或只复制 `code` 参数，再回到服务器交换 Refresh Token：

```powershell
nyagallery --storage storage pixiv-oauth-exchange --code-verifier "上一步输出的 code_verifier" --callback-url "最终 callback URL" --plain
```

如果你只拿到了 `code`：

```powershell
nyagallery --storage storage pixiv-oauth-exchange --code-verifier "上一步输出的 code_verifier" --code "your-code" --plain
```

设置临时环境变量：

```powershell
$env:PIXIV_REFRESH_TOKEN = "your-refresh-token"
```

使用登录态抓取单个作品：

```powershell
nyagallery --storage storage pixiv-sync-pid 123456 --auth-mode refresh-token --generate-cache --rebuild-db
```

使用登录态抓取用户作品：

```powershell
nyagallery --storage storage pixiv-sync-user 88888 --auth-mode refresh-token --limit 50 --generate-cache --rebuild-db
```

## 9. 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

## 10. 从头再来

保留原图和 metadata，只重建数据库：

```powershell
Remove-Item storage\nyagallery.db
nyagallery --storage storage rebuild-db
```

彻底重置本地数据：

```powershell
Remove-Item storage -Recurse
nyagallery --storage storage setup --username admin --role admin --password 123123
```
