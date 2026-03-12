import os
import sys
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

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
    
    # 强制在测试期间将所有数据写入系统临时目录
    test_run_root = Path("/tmp/webrpa_test_run")
    if test_run_root.exists():
        shutil.rmtree(test_run_root)
    test_run_root.mkdir(parents=True, exist_ok=True)
    
    # 模拟必要的目录结构
    (test_run_root / "config" / "data").mkdir(parents=True, exist_ok=True)
    (test_run_root / "plugins").mkdir(parents=True, exist_ok=True)

    source_devices = project_root / "config" / "devices.json"
    target_devices = test_run_root / "config" / "devices.json"
    if source_devices.exists():
        _ = shutil.copyfile(source_devices, target_devices)
    else:
        _ = target_devices.write_text("{}", encoding="utf-8")

    # 关键：通过环境变量重定向根目录
    os.environ["MYT_NEW_ROOT"] = str(test_run_root)
    
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
