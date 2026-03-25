import os
import shutil
import sys
import time
from collections.abc import Generator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

import core.config_loader as config_loader
from api.server import app
from engine.action_registry import reset_registry
from engine.plugin_loader import clear_shared_plugin_loader_cache


def pytest_sessionstart(session: object) -> None:
    _ = session
    project_root = Path(__file__).resolve().parents[1]

    # 柔性硬件保护逻辑：
    # 1. 如果用户显式想测硬件 (MYT_REAL_HARDWARE=1)，则尊重用户设置
    # 2. 否则，为了安全起见，在测试期间强制禁用 RPC
    if os.environ.get("MYT_REAL_HARDWARE") != "1":
        os.environ["MYT_ENABLE_RPC"] = "0"

    # 测试隔离：把所有 runtime 数据写入 config/data/<subdir>（仍在仓库内，但与真实数据隔离）
    run_tag = f".pytest/run-{os.getpid()}-{time.time_ns()}"
    os.environ["MYT_DATA_SUBDIR"] = run_tag
    test_data_dir = project_root / "config" / "data" / run_tag
    if test_data_dir.exists():
        shutil.rmtree(test_data_dir)
    test_data_dir.mkdir(parents=True, exist_ok=True)

    project_parent = project_root.parent
    parent_text = str(project_parent)
    if parent_text not in sys.path:
        sys.path.insert(0, parent_text)


@pytest.fixture(autouse=True)
def isolate_engine_globals() -> Generator[None, None, None]:
    clear_shared_plugin_loader_cache()
    reset_registry()
    yield
    clear_shared_plugin_loader_cache()
    reset_registry()


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_lifespan: run the FastAPI app with its real lifespan hooks enabled",
    )


@pytest.fixture(autouse=True)
def disable_app_lifespan_by_default(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Generator[None, None, None]:
    if request.node.get_closest_marker("real_lifespan") is None:
        monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)
    yield


@pytest.fixture(autouse=True)
def isolate_config_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[None, None, None]:
    test_config_path = tmp_path / "devices.json"
    backup_cache = config_loader.ConfigLoader._config
    monkeypatch.setattr(config_loader, "CONFIG_FILE", test_config_path)
    config_loader.ConfigLoader._config = None
    yield
    config_loader.ConfigLoader._config = backup_cache
