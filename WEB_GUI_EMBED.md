# Web as GUI Embed Guide

This project supports using the web frontend as a desktop GUI by embedding `/web` in a webview.

## Target URL
- `http://127.0.0.1:8000/web`

## Recommended Flow
1. Start backend service.
2. Open desktop shell window with embedded webview.
3. Load `/web` URL inside embedded view.

## Option A: pywebview (lightweight)

```python
import threading
import webview
import uvicorn


def run_api():
    uvicorn.run("new.api.server:app", host="127.0.0.1", port=8000)


threading.Thread(target=run_api, daemon=True).start()
webview.create_window("MYT Console", "http://127.0.0.1:8000/web", width=1280, height=820)
webview.start()
```

## Option B: Flet/Flutter shell
- Start API in background process.
- Create desktop window with webview widget.
- Point widget URL to `/web`.

## Option C: Electron shell
- Keep FastAPI as backend.
- BrowserWindow loads `http://127.0.0.1:8000/web`.

## Stability Notes
- Health endpoint must return 200 before creating webview.
- Reconnect websocket logs automatically in frontend (`/ws/logs`).
- Keep API and webview in same host to avoid CORS complexity.
