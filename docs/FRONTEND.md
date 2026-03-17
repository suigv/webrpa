# Frontend (Vite) — API-only Backend Deployment

This project now treats the backend (`api/server.py`) as **API-only**.
The Web console is a separate frontend app (Vite) under `web/` and should be served by **Nginx**.

## Local development

Backend (API):

```bash
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Frontend (Vite):

```bash
cd web
npm install
npm run dev
```

Vite dev server proxies `/api`, `/health`, and `/ws` to `http://127.0.0.1:8001` by default.

## Production build

```bash
cd web
npm install
npm run build
```

Build output is written to `web/dist/` (not committed).

## Nginx (single-host reverse proxy)

Recommended layout:

- Nginx serves the frontend static files (`web/dist/`)
- Nginx proxies backend API endpoints to `127.0.0.1:8001`

Example (adjust paths and domain):

```nginx
server {
  listen 80;
  server_name _;

  # Frontend build output
  root /path/to/webrpa/web/dist;
  index index.html;

  # SPA fallback
  location / {
    try_files $uri $uri/ /index.html;
  }

  # Keep /web as the canonical console entry
  location = /web {
    return 302 /;
  }

  # API reverse proxy
  location /api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location = /health {
    proxy_pass http://127.0.0.1:8001/health;
  }

  # WebSocket reverse proxy
  location /ws/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
  }
}
```

## Auth note (JWT)

Browser constraints matter:

- `fetch()` can send `Authorization: Bearer <jwt>`
- `EventSource` (SSE) **cannot** set custom headers
- `WebSocket` custom headers are not portable

If you need JWT auth on SSE/WS, prefer **JWT in HttpOnly Cookie** (still JWT, but transported via cookie), or implement a header-capable SSE client (manual parsing) and a WS token handshake.

