# Frontend (Vite) — API-only Backend Deployment

This project now treats the backend (`api/server.py`) as **API-only**.
The Web console is a separate frontend app (Vite) under `web/` and should be served by **Nginx**.

## Local development

Backend (API):

```bash
./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

One-click (recommended):

```bash
./run_webrpa.sh
```

Frontend (Vite):

```bash
cd web
npm install
npm run dev
```

Vite dev server proxies `/api`, `/health`, and `/ws` to `http://127.0.0.1:8001` by default.

If you need a pure-web fallback (no devices / no native libs), start backend with `MYT_ENABLE_RPC=0`.

## Task payload contract

- Frontend task forms must be rendered from `GET /api/tasks/catalog` metadata rather than hardcoded field lists.
- Frontend task submission must treat `manifest.inputs` as the only allowed plugin payload schema.
- Do not inject implicit payload fields such as `app_id`, `device_ip`, `package`, account aliases, or target metadata unless the selected plugin explicitly declares them in `inputs`.
- Runtime context belongs in dedicated channels such as `targets` and backend-owned runtime envelopes, not in plugin `payload`.
- Shared runtime payload knobs such as `_speed`, `_wait_min_ms`, and `_wait_max_ms` should stay aligned between the main task queue form and device-scoped task forms.
- If a page needs task-specific context, add it to the plugin manifest first or route it through a non-payload contract; do not create page-local exceptions.
- Current backend still carries a small deprecated compatibility seam for legacy `device_ip` payload fallback. Treat that as migration-only behavior: frontend code must not rely on it or reintroduce it.

## Workflow drafts (history + replay)

- The Web console includes a “草稿历史” panel that reads workflow draft state from:
  - `GET /api/tasks/drafts`
  - `GET /api/tasks/drafts/{draft_id}`
  - `GET /api/tasks/drafts/{draft_id}/snapshot` (edit-and-replay form prefill)
- Continuing validation and distillation are triggered via:
  - `POST /api/tasks/drafts/{draft_id}/continue`
  - `POST /api/tasks/drafts/{draft_id}/distill`

## AI execution overlay

- Device-detail AI dialog submissions should open the execution overlay with the bound unit context.
- The execution overlay now embeds the same screenshot preview and light controls used by the device detail page.
- When AI pauses for intervention, operators should be able to inspect the current cloud screen, request takeover, perform light controls, and then resume from the same overlay.
- If the operator closes the execution overlay while the same unit still has a running/paused AI task, clicking `AI 对话` again should reopen that execution overlay instead of starting a fresh submission form.
- Device inventory reads should converge through a shared frontend snapshot instead of each feature directly polling `/api/devices/`; screenshot surfaces should pause refresh while the page is hidden to reduce backend pressure.

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

## Current `/web` behavior

- The backend does **not** serve the Vite build directly.
- `GET /web` is only a console entry shim:
  - if `MYT_FRONTEND_URL` is set, backend returns `307` redirect to that URL;
  - otherwise backend returns `501` with frontend deployment guidance.
- Browser hands-on verification of the operator console is therefore still distinct from backend API verification.

## Planned: Device WebRTC takeover

The device detail page currently uses backend-mediated screenshots for the "current screen" panel.
A future goal is to add a WebRTC-based live takeover mode for real-time monitoring and control, while keeping screenshot preview as a fallback.

Before that work is scheduled, keep these constraints in mind:

- The current Vite production build does not emit `web/webplayer/play.html` or its JS assets into `web/dist/`; they must be published explicitly if WebRTC takeover is enabled.
- The browser must be able to reach the device WebRTC endpoints directly; this is a different network model from the current screenshot API, which is proxied through the backend.
- WebRTC takeover should consume backend-issued connection metadata or short-lived access material rather than hardcoded frontend port formulas.
- Production rollout must account for HTTPS/WSS compatibility, auth propagation, and operation audit boundaries for direct interactive control.

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
