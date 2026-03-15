import logging
import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes import config as config_route
from api.routes import data as data_route
from api.routes import devices as devices_route
from api.routes import task_routes as tasks_route
from api.routes import websocket as websocket_route
from api.routes import engine_routes
from api.routes import binding_routes as binding_route
from core.device_manager import get_device_manager
from core.cloud_probe_service import get_cloud_probe_service
from core.paths import project_root
from core.task_control import get_task_controller
from engine.actions._rpc_bootstrap import is_rpc_enabled
from engine.runner import Runner, strict_plugin_unknown_inputs_enabled
from hardware_adapters.browser_client import BrowserClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def _cleanup_stale_browser_profiles() -> None:
    from core.paths import browser_profiles_dir
    base_dir = browser_profiles_dir()
    if not base_dir.exists():
        return
    cutoff = time.time() - 3600
    cleaned = 0
    for d in base_dir.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            cleaned += 1
    if cleaned:
        logging.info(f"Cleaned up {cleaned} stale browser profile(s) from {base_dir}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 注册 WebSocket 日志广播桥接
    import asyncio
    from api.routes.websocket import get_event_broadcaster, start_db_event_poller, stop_db_event_poller
    controller = get_task_controller()
    loop = asyncio.get_running_loop()
    observer = get_event_broadcaster(loop)
    subscribe_events = getattr(controller, "subscribe_events", None)
    if callable(subscribe_events):
        subscribe_events(observer)
    else:
        # Backwards-compat for older controller shapes / test fakes.
        events = getattr(controller, "_events", None)
        legacy_subscribe = getattr(events, "subscribe", None) if events is not None else None
        if not callable(legacy_subscribe):
            raise RuntimeError("Task controller does not support event subscription")
        legacy_subscribe(observer)
    start_db_event_poller(loop)

    # 清理残留的 browser profile 目录（超过 1 小时未修改的视为泄露）
    _cleanup_stale_browser_profiles()

    device_manager = get_device_manager()
    device_manager.validate_topology_or_raise()
    controller = get_task_controller()
    controller.start()
    probe_service = get_cloud_probe_service()
    probe_service.start()
    try:
        yield
    finally:
        probe_service.stop()
        controller.stop()
        stop_db_event_poller()


app = FastAPI(title="MYT New Standalone API", version="0.1.0", lifespan=lifespan)
WEB_DIR = project_root() / "web"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices_route.router, prefix="/api/devices", tags=["devices"])
app.include_router(tasks_route.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(config_route.router, prefix="/api/config", tags=["config"])
app.include_router(data_route.router, prefix="/api/data", tags=["data"])
app.include_router(engine_routes.router, prefix="/api/engine", tags=["engine"])
app.include_router(binding_route.router, prefix="/api/binding", tags=["binding"])
app.include_router(websocket_route.router)

# Mount static files first
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def root():
    return RedirectResponse(url="/web", status_code=307)


@app.get("/web", include_in_schema=False)
def web_index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health():
    rpc_enabled = is_rpc_enabled()
    from engine.plugin_loader import get_shared_plugin_loader
    loader = get_shared_plugin_loader()
    loaded_plugins = loader.names
    return {
        "status": "ok",
        "runtime": "skeleton",
        "rpc_enabled": rpc_enabled,
        "task_policy": {
            "strict_plugin_unknown_inputs": strict_plugin_unknown_inputs_enabled(),
            "stale_running_seconds": _stale_running_seconds(),
        },
        "plugins": {
            "loaded": loaded_plugins,
            "count": len(loaded_plugins),
        },
    }


def _stale_running_seconds() -> int:
    raw = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS", "300").strip()
    try:
        parsed = int(raw)
    except ValueError:
        return 300
    return max(0, parsed)


@app.post(
    "/api/runtime/execute",
    summary="Debug-only direct runtime execute",
    description=(
        "Internal/debug direct-run path. Executes the payload synchronously and returns the raw Runner result "
        "without creating managed task records or participating in the /api/tasks lifecycle. Retries, "
        "cancellation flow, SSE task events, and task metrics artifacts remain exclusive to /api/tasks."
    ),
)
def execute_runtime(payload: dict[str, object]):
    runner = Runner()
    return runner.run(payload)


@app.get("/api/diagnostics/browser")
def browser_diagnostics():
    return BrowserClient.startup_diagnostics()
