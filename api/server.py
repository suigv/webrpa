import logging
import os
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
from core.device_manager import DeviceManager
from core.lan_discovery import LanDeviceDiscovery
from core.task_control import get_task_controller
from engine.runner import Runner, strict_plugin_unknown_inputs_enabled
from hardware_adapters.browser_client import BrowserClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    device_manager = DeviceManager()
    discovery = LanDeviceDiscovery()
    discovery.start()
    device_manager.validate_topology_or_raise()
    controller = get_task_controller()
    controller.start()
    device_manager.start_cloud_probe_worker()
    try:
        yield
    finally:
        device_manager.stop_cloud_probe_worker()
        controller.stop()
        discovery.stop()


app = FastAPI(title="MYT New Standalone API", version="0.1.0", lifespan=lifespan)
WEB_DIR = Path(__file__).resolve().parents[1] / "web"

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
    rpc_enabled = os.environ.get("MYT_ENABLE_RPC", "0") == "1"
    return {
        "status": "ok",
        "runtime": "skeleton",
        "rpc_enabled": rpc_enabled,
        "task_policy": {
            "strict_plugin_unknown_inputs": strict_plugin_unknown_inputs_enabled(),
            "stale_running_seconds": _stale_running_seconds(),
        },
    }


def _stale_running_seconds() -> int:
    raw = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS", "300").strip()
    try:
        parsed = int(raw)
    except ValueError:
        return 300
    return max(0, parsed)


@app.post("/api/runtime/execute")
def execute_runtime(payload: dict[str, object]):
    runner = Runner()
    return runner.run(payload)


@app.get("/api/diagnostics/browser")
def browser_diagnostics():
    return BrowserClient.startup_diagnostics()
