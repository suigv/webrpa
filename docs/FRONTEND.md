---
doc_type: current
source_of_truth: current
owner: repo
last_verified_at: 2026-03-24
stale_after_days: 14
verification_method:
  - web/ tree audit
  - backend /web behavior audit
---

# Frontend

当前前端是 `web/` 下的独立 Vite 工程。后端不是前端静态文件服务器。

## 本地开发

后端：

```bash
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

前端：

```bash
cd web
npm install
npm run dev
```

如需无 RPC 的纯 Web 路径：

```bash
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

## 部署边界

- 前端构建产物位于 `web/dist/`。
- 推荐由 Nginx 或其他静态服务器托管 `web/dist/`。
- 后端保留 `/web` 作为入口路由：
  - 配置 `MYT_FRONTEND_URL` 时重定向到前端地址。
  - 未配置时返回部署提示。

## 前端任务提交契约

- 任务表单应来自 `GET /api/tasks/catalog`。
- 插件提交必须遵守 `manifest.inputs` 白名单。
- `targets` 承载目标设备上下文。
- 不要让前端重新把 `device_ip`、`package`、目标元数据之类的运行时字段塞回插件 `payload`。

## 鉴权

启用 JWT 时：

- HTTP 使用 `Authorization: Bearer <jwt>`
- 浏览器 WebSocket 使用 `Sec-WebSocket-Protocol: bearer.<jwt>`
