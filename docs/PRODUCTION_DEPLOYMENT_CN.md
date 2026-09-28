# NyaGallery 生产部署指南

本文面向长期运行、需要公网或局域网访问的部署。建议先完成 [快速启动](QUICKSTART_CN.md)，再按本文把开发服务器替换为受控进程、反向代理、HTTPS 和备份流程。

## 1. 推荐架构

```text
浏览器 ── HTTPS ── nginx/Caddy ── Next.js :3000 ── FastAPI :8001
                                      │
                                      ├─ storage/original（原图）
                                      ├─ storage/metadata、tags（可重建索引）
                                      └─ SQLite 或 PostgreSQL；可选 Redis
```

公网环境不要直接暴露 FastAPI 或 Next.js 的开发服务器。后端只监听 `127.0.0.1`，由反向代理负责 TLS、域名、压缩和外部访问控制。原图、metadata 和标签目录必须放在持久化磁盘上。

## 2. Linux 部署

### 2.1 创建用户和目录

```bash
sudo useradd --system --home /opt/nyagallery --shell /usr/sbin/nologin nyagallery
sudo mkdir -p /opt/nyagallery/app /srv/nyagallery/storage
sudo chown -R nyagallery:nyagallery /opt/nyagallery /srv/nyagallery
```

在 `/opt/nyagallery/app` 部署代码，在虚拟环境中安装依赖：

```bash
cd /opt/nyagallery/app
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[media,pixiv,pixiv-login,postgres,redis]"
cd frontend
corepack enable
corepack prepare pnpm@11.13.1 --activate
pnpm install --frozen-lockfile
pnpm run build
command -v pnpm
```

记录 `command -v pnpm` 输出的绝对路径。下面的 systemd 示例假设它是 `/usr/bin/pnpm`；如果实际路径不同，必须同步替换 `ExecStart`，并确保服务用户可以执行该文件。

初始化时使用绝对存储目录：

```bash
sudo -u nyagallery /opt/nyagallery/app/.venv/bin/nyagallery \
  --config /etc/nyagallery/nyagallery.toml \
  setup --username admin --role admin
```

### 2.2 systemd 后端服务

`/etc/systemd/system/nyagallery-api.service`：

```ini
[Unit]
Description=NyaGallery FastAPI
After=network-online.target
Wants=network-online.target

[Service]
User=nyagallery
Group=nyagallery
WorkingDirectory=/opt/nyagallery/app
Environment=NYAGALLERY_CONFIG=/etc/nyagallery/nyagallery.toml
Environment=NYAGALLERY_HOST=127.0.0.1
Environment=NYAGALLERY_PORT=8001
ExecStart=/opt/nyagallery/app/.venv/bin/nyagallery serve
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/srv/nyagallery/storage

[Install]
WantedBy=multi-user.target
```

### 2.3 systemd 前端服务

`/etc/systemd/system/nyagallery-web.service`：

```ini
[Unit]
Description=NyaGallery Next.js
After=network-online.target nyagallery-api.service

[Service]
User=nyagallery
Group=nyagallery
WorkingDirectory=/opt/nyagallery/app/frontend
Environment=NODE_ENV=production
Environment=NYA_API_BACKEND=http://127.0.0.1:8001
ExecStart=/usr/bin/pnpm run start -- -H 127.0.0.1 -p 3000
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nyagallery-api nyagallery-web
sudo systemctl status nyagallery-api nyagallery-web
curl http://127.0.0.1:8001/health
```

### 2.4 nginx 反向代理

```nginx
server {
    listen 80;
    server_name gallery.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name gallery.example.com;
    # 证书配置由 certbot 或发行版工具生成

    client_max_body_size 512m;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

启用 HTTPS 后，在配置中设置 `server.secure_cookies = true`。如果 nginx 位于另一层代理之后，只有确认代理可信时才打开 `trust_proxy_headers`，否则客户端 IP 和 Origin 可能被伪造。该运行时安全项通过 CLI 调整：

```bash
nyagallery --storage /srv/nyagallery/storage security-config \
  --trust-proxy-headers on \
  --trusted-origin https://gallery.example.com
```

## 3. Windows 生产部署

使用独立 Python 虚拟环境和 Node.js 22.13+。前端使用 `pnpm@11.13.1`，执行 `pnpm install --frozen-lockfile`、`pnpm run build` 和 `pnpm run start -- -H 127.0.0.1 -p 3000`；后端执行 `nyagallery serve --host 127.0.0.1 --port 8001`。可使用 NSSM、WinSW 或任务计划程序分别托管两个进程；服务账户需要对 storage 目录拥有读写权限。

Windows 路径建议写成 `D:/NyaGallery/storage` 或 `D:/NyaGallery/original`。如果后端运行在 Docker/WSL，填写的是容器或 Linux 环境内路径，不是 Windows 浏览器所在机器的路径。

## 4. 数据库、Redis 与扩展

- SQLite 适合单实例和中小规模；数据库文件应与原图一起备份，但不要放在网络盘上。
- PostgreSQL 通过 `[core].database_url` 或 `NYAGALLERY_DATABASE_URL` 配置，例如 `postgresql+psycopg://user:pass@db/nyagallery`。
- 多个后端实例共享限流状态时配置 `[redis].url` 和 `security_limiter = true`。Redis 不是原图存储，也不能替代备份。
- 多实例写入同一套本地原图目录时必须使用共享、可靠且具有锁语义的文件系统；更稳妥的方案是单写入实例或远程对象存储策略。

## 5. 备份与恢复

必须备份：

```text
storage/original/      # 原图，不可重建
storage/metadata/      # 资源元数据
storage/tags/          # 标签目录
nyagallery.toml        # 配置（妥善保护密钥）
```

`preview/`、`thumbs/` 和数据库索引可以重建，但生产上仍建议定期备份 `storage/nyagallery.db` 或 PostgreSQL 数据库以缩短恢复时间。恢复顺序通常是还原原图、metadata、tags，启动服务后执行：

```bash
nyagallery --config /etc/nyagallery/nyagallery.toml rebuild-db --generate-cache
```

`[security].secret_key`（或 `NYAGALLERY_SECRET_KEY`）必须和备份中的配置保持一致，否则已加密的第三方凭据无法解密。

## 6. 升级与回滚

1. 先备份原图、metadata、tags、配置和数据库。
2. 停止 web/API 服务，保留 storage 不动。
3. 更新代码和依赖，执行前端 `pnpm install --frozen-lockfile && pnpm run build`。
4. 启动 API，检查 `/health`、登录、搜索和一张原图，再启动 web。
5. 如升级失败，恢复代码和依赖版本；不要用空目录覆盖 storage。

升级后若索引异常，使用 `rebuild-db`；缓存异常，使用 `generate-cache`。重建不会修改原图。

## 7. 生产检查清单

- [ ] 后端未直接暴露到公网，HTTPS 和安全 Cookie 已启用。
- [ ] `secret_key` 已生成、备份且权限为仅服务账户可读。
- [ ] 原图目录有足够空间，服务账户可读写。
- [ ] nginx `client_max_body_size` 大于应用上传限制。
- [ ] 已创建非 admin 的日常账号，API Token 使用最小权限。
- [ ] 已验证备份可读、`/health` 可用、登录和原图下载正常。
- [ ] 已配置日志轮转、磁盘监控和失败服务告警。
