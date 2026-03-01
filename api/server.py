import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from new.api.routes import config as config_route
from new.api.routes import data as data_route
from new.api.routes import devices as devices_route
from new.api.routes import websocket as websocket_route
from new.engine.runner import Runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="MYT New Standalone API", version="0.1.0")
WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices_route.router, prefix="/api/devices", tags=["devices"])
app.include_router(config_route.router, prefix="/api/config", tags=["config"])
app.include_router(data_route.router, prefix="/api/data", tags=["data"])
app.include_router(websocket_route.router)
app.mount("/web", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


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
    }


@app.post("/api/runtime/execute")
def execute_runtime(payload: dict[str, object]):
    runner = Runner()
    return runner.run(payload)
