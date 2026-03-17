# Frontend (Vite) — API-only Backend Deployment

This project now treats the backend (`api/server.py`) as **API-only**.
The Web console is a separate frontend app (Vite) under `web/` and should be served by **Nginx**.

## Local development

Backend (API):

```bash
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Frontend (Vite):

```bash
cd web
npm install
npm run dev
```

Vite dev server proxies `/api`, `/health`, and `/ws` to `http://127.0.0.1:8001` by default.

If you need a pure-web fallback (no devices / no native libs), start backend with `MYT_ENABLE_RPC=0`.

## Editor / TypeScript language server

If your editor needs `typescript-language-server`:

```bash
npm i -g typescript typescript-language-server
```

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
    # If you stream SSE, buffering can delay events.
    proxy_buffering off;
  }

  location = /health {
    proxy_pass http://127.0.0.1:8001/health;
  }

  # Optional: keep /docs reachable; protect /openapi.json via MYT_AUTH_PROTECT_OPENAPI=1.
  location = /openapi.json {
    proxy_pass http://127.0.0.1:8001/openapi.json;
  }

  # WebSocket reverse proxy
  location /ws/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    # Ensure subprotocol (bearer.<jwt>) is forwarded.
    proxy_set_header Sec-WebSocket-Protocol $http_sec_websocket_protocol;
  }
}
```

## Auth note (JWT)

Browser constraints matter:

- `fetch()` can send `Authorization: Bearer <jwt>`
- Native `EventSource` (SSE) **cannot** set custom headers (this repo uses a fetch-based SSE client so the Bearer header is sent)
- Browser `WebSocket` cannot reliably send `Authorization` headers (this repo passes the JWT via `Sec-WebSocket-Protocol: bearer.<jwt>`)

Backend env vars:

- `MYT_AUTH_MODE=jwt` to enable auth (default: disabled)
- `MYT_JWT_SECRET=...` shared secret for `HS256` verification
- `MYT_JWT_ALGORITHMS=HS256` (comma-separated)
- Optional: `MYT_JWT_ISSUER`, `MYT_JWT_AUDIENCE`, `MYT_JWT_LEEWAY_SECONDS`, `MYT_JWT_REQUIRE_EXP=1`
- Optional: `MYT_AUTH_PROTECT_OPENAPI=1` to require Bearer token for `/openapi.json`

## Token generation (offline)

Generate a strong secret (recommended >= 32 bytes):

```bash
./.venv/bin/python tools/generate_jwt.py --random-secret
```

Generate a JWT (reads `MYT_JWT_SECRET` by default):

```bash
MYT_JWT_SECRET='...' ./.venv/bin/python tools/generate_jwt.py --sub operator --ttl-seconds 86400
```

Use it in the web console:

- HTTP: `Authorization: Bearer <jwt>`
- WebSocket: `Sec-WebSocket-Protocol: bearer.<jwt>`
