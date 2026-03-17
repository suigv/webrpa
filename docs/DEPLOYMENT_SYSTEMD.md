# Deployment (systemd) — API-only Backend + Nginx

目标：后端只作为 API，前端由 Nginx 提供静态站点并反向代理 API/WS。

## 1) systemd unit（后端）

示例：`/etc/systemd/system/webrpa.service`

```ini
[Unit]
Description=webrpa api
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/webrpa
Environment=PYTHONPATH=/opt/webrpa
Environment=MYT_LOAD_DOTENV=1
Environment=MYT_ENABLE_RPC=0
Environment=MYT_TASK_QUEUE_BACKEND=redis
Environment=MYT_AUTH_MODE=jwt
Environment=MYT_AUTH_PROTECT_OPENAPI=1
ExecStart=/opt/webrpa/.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001 --log-level info
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

操作：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now webrpa
sudo systemctl status webrpa --no-pager
curl -sS http://127.0.0.1:8001/health
```

## 2) Nginx

按 `docs/FRONTEND.md` 的示例配置即可。注意：

- SSE 建议 `proxy_buffering off;`（避免事件被缓冲）
- WebSocket 若使用 `Sec-WebSocket-Protocol: bearer.<jwt>`，建议显式转发 `Sec-WebSocket-Protocol` 头

## 3) JWT secret 建议

请确保 `MYT_JWT_SECRET` 至少 32 bytes（否则 PyJWT 会告警）。

生成 secret：

```bash
./.venv/bin/python tools/generate_jwt.py --random-secret
```

