import importlib
import json
import multiprocessing
import threading
import time

from core.paths import data_dir


def _load_action_registry_module():
    for name in ("engine.action_registry", "engine.action_registry"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import action_registry module")


def _load_execution_context():
    for name in ("engine.models.runtime", "engine.models.runtime"):
        try:
            return importlib.import_module(name).ExecutionContext
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import ExecutionContext")


def _cross_process_update_worker(
    ready_event,
    release_event,
    key: str,
    value: int,
) -> None:
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")

    def updater(store):
        if ready_event is not None:
            ready_event.set()
        if release_event is not None:
            release_event.wait(timeout=2)
        store[key] = value

    sdk_mod._update_store(updater)


def test_registry_contains_sdk_and_mytos_actions(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()
    assert reg.has("sdk.get_device_info")
    assert reg.has("sdk.start_android")
    assert reg.has("mytos.query_s5_proxy")
    assert reg.has("mytos.set_clipboard")


def test_sdk_action_invocation_maps_to_client(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    class FakeSdkClient:
        def __init__(
            self,
            device_ip: str,
            sdk_port: int = 8000,
            timeout_seconds: float = 30.0,
            retries: int = 3,
        ):
            self.device_ip = device_ip
            self.sdk_port = sdk_port

        def get_device_info(self):
            return {"ok": True, "data": {"ip": self.device_ip, "port": self.sdk_port}}

    class FakeAndroidApiClient:
        def __init__(
            self, device_ip: str, api_port: int, timeout_seconds: float = 30.0, retries: int = 3
        ):
            self.device_ip = device_ip
            self.api_port = api_port

        def set_clipboard(self, text: str):
            return {"ok": True, "data": {"text": text}}

        def ip_geolocation(self, ip: str = "", language: str = ""):
            return {"ok": True, "data": {"ip": ip, "language": language}}

        def screenshot(
            self, image_type: int = 0, quality: int = 80, save_path: str = "", level=None
        ):
            return {
                "ok": True,
                "data": {"level": level, "image_type": image_type, "quality": quality},
            }

        def set_device_fingerprint(self, data):
            return {"ok": True, "data": {"fingerprint": data}}

        def set_shake(self, enabled: bool | None = None, shake=None):
            return {"ok": True, "data": {"enabled": enabled, "shake": shake}}

    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    android_mod = importlib.import_module("engine.actions.android_api_actions")
    monkeypatch.setattr(sdk_mod, "MytSdkClient", FakeSdkClient)
    monkeypatch.setattr(android_mod, "AndroidApiClient", FakeAndroidApiClient)

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.8", "sdk_port": 8010}, runtime={"api_port": 30001}
    )
    res1 = reg.resolve("sdk.get_device_info")({}, ctx)
    assert res1.ok is True
    assert res1.data["result"]["data"]["ip"] == "192.168.1.8"

    # mytos.set_clipboard now uses 'text' param (30001 API)
    res2 = reg.resolve("mytos.set_clipboard")({"text": "abc"}, ctx)
    assert res2.ok is True

    res3 = reg.resolve("mytos.ip_geolocation")({"ip": "23.247.138.215"}, ctx)
    assert res3.ok is True

    res4 = reg.resolve("mytos.screenshot")({"level": 3}, ctx)
    assert res4.ok is True
    assert res4.data["level"] == 3

    res5 = reg.resolve("mytos.set_fingerprint")({"data": {"imei": "123"}}, ctx)
    assert res5.ok is True

    res6 = reg.resolve("mytos.set_shake")({"enabled": False}, ctx)
    assert res6.ok is True


def test_android_api_actions_keepalive_and_google_paths(monkeypatch):
    android_mod = importlib.import_module("engine.actions.android_api_actions")
    ExecutionContext = _load_execution_context()
    calls: list[tuple[str, object]] = []

    class FakeAndroidApiClient:
        def __init__(
            self, device_ip: str, api_port: int, timeout_seconds: float = 30.0, retries: int = 3
        ):
            self.device_ip = device_ip
            self.api_port = api_port

        def query_background_keepalive(self):
            calls.append(("query_background_keepalive", None))
            return {"ok": True, "data": {"items": []}}

        def add_background_keepalive(self, package: str):
            calls.append(("add_background_keepalive", package))
            return {"ok": True, "data": {"package": package}}

        def remove_background_keepalive(self, package: str):
            calls.append(("remove_background_keepalive", package))
            return {"ok": True, "data": {"package": package}}

        def update_background_keepalive(self, package: str):
            calls.append(("update_background_keepalive", package))
            return {"ok": True, "data": {"package": package}}

        def get_google_id(self, cmd=None):
            calls.append(("get_google_id", cmd))
            return {"ok": True, "data": {"cmd": cmd}}

    monkeypatch.setattr(android_mod, "AndroidApiClient", FakeAndroidApiClient)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.9"}, runtime={"api_port": 30001})

    assert android_mod.android_query_background_keepalive({}, ctx).ok is True
    assert android_mod.android_add_background_keepalive({"package": "pkg.demo"}, ctx).ok is True
    assert android_mod.android_remove_background_keepalive({"package": "pkg.demo"}, ctx).ok is True
    assert android_mod.android_update_background_keepalive({"package": "pkg.demo"}, ctx).ok is True
    assert android_mod.android_get_google_adid({}, ctx).ok is True
    assert android_mod.android_get_google_id({"cmd": 2}, ctx).ok is True

    missing_package = android_mod.android_add_background_keepalive({}, ctx)
    assert missing_package.ok is False
    assert missing_package.code == "invalid_params"

    assert calls == [
        ("query_background_keepalive", None),
        ("add_background_keepalive", "pkg.demo"),
        ("remove_background_keepalive", "pkg.demo"),
        ("update_background_keepalive", "pkg.demo"),
        ("get_google_id", None),
        ("get_google_id", 2),
    ]


def test_android_api_actions_zero_arg_wrappers(monkeypatch):
    android_mod = importlib.import_module("engine.actions.android_api_actions")
    ExecutionContext = _load_execution_context()
    calls: list[str] = []

    class FakeAndroidApiClient:
        def __init__(
            self, device_ip: str, api_port: int, timeout_seconds: float = 30.0, retries: int = 3
        ):
            self.device_ip = device_ip
            self.api_port = api_port

        def get_clipboard(self):
            calls.append("get_clipboard")
            return {"ok": True, "data": {"result": "clipboard"}}

        def query_s5_proxy(self):
            calls.append("query_s5_proxy")
            return {"ok": True, "data": {"enabled": True}}

        def stop_s5_proxy(self):
            calls.append("stop_s5_proxy")
            return {"ok": True, "data": {}}

        def refresh_location(self):
            calls.append("refresh_location")
            return {"ok": True, "data": {}}

        def get_container_info(self):
            calls.append("get_container_info")
            return {"ok": True, "data": {"name": "android-01"}}

        def get_version(self):
            calls.append("get_version")
            return {"ok": True, "data": {"version": "1.0.0"}}

        def get_boot_apps(self):
            calls.append("get_boot_apps")
            return {"ok": True, "data": {"packages": []}}

        def get_root_allowed_apps(self):
            calls.append("get_root_allowed_apps")
            return {"ok": True, "data": {"packages": []}}

    monkeypatch.setattr(android_mod, "AndroidApiClient", FakeAndroidApiClient)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.10"}, runtime={"api_port": 30001})

    assert android_mod.android_get_clipboard({}, ctx).ok is True
    assert android_mod.android_query_proxy({}, ctx).ok is True
    assert android_mod.android_stop_proxy({}, ctx).ok is True
    assert android_mod.android_refresh_location({}, ctx).ok is True
    assert android_mod.android_get_container_info({}, ctx).ok is True
    assert android_mod.android_get_version({}, ctx).ok is True
    assert android_mod.android_get_app_bootstart_list({}, ctx).ok is True
    assert android_mod.android_get_root_allowed_apps({}, ctx).ok is True

    assert calls == [
        "get_clipboard",
        "query_s5_proxy",
        "stop_s5_proxy",
        "refresh_location",
        "get_container_info",
        "get_version",
        "get_boot_apps",
        "get_root_allowed_apps",
    ]


def test_android_api_actions_backup_restore_aliases(monkeypatch):
    android_mod = importlib.import_module("engine.actions.android_api_actions")
    ExecutionContext = _load_execution_context()
    calls: list[tuple[str, str, str]] = []

    class FakeAndroidApiClient:
        def __init__(
            self, device_ip: str, api_port: int, timeout_seconds: float = 30.0, retries: int = 3
        ):
            self.device_ip = device_ip
            self.api_port = api_port

        def backup_app(self, package: str, save_to: str):
            calls.append(("backup_app", package, save_to))
            return {"ok": True, "data": {"package": package, "save_to": save_to}}

        def restore_app(self, backup_path: str):
            calls.append(("restore_app", backup_path, ""))
            return {"ok": True, "data": {"backup_path": backup_path}}

    monkeypatch.setattr(android_mod, "AndroidApiClient", FakeAndroidApiClient)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.11"}, runtime={"api_port": 30001})

    assert (
        android_mod.android_backup_app({"pkg": "pkg.demo", "saveto": "/tmp/a.bak"}, ctx).ok is True
    )
    assert (
        android_mod.android_export_app_info(
            {"package": "pkg.demo", "save_to": "/tmp/b.bak"}, ctx
        ).ok
        is True
    )
    assert android_mod.android_restore_app({"backuppath": "/tmp/a.bak"}, ctx).ok is True
    assert android_mod.android_import_app_info({"backup_path": "/tmp/b.bak"}, ctx).ok is True

    missing_backup = android_mod.android_backup_app({}, ctx)
    missing_restore = android_mod.android_import_app_info({}, ctx)
    assert missing_backup.ok is False
    assert missing_backup.code == "invalid_params"
    assert missing_restore.ok is False
    assert missing_restore.code == "invalid_params"

    assert calls == [
        ("backup_app", "pkg.demo", "/tmp/a.bak"),
        ("backup_app", "pkg.demo", "/tmp/b.bak"),
        ("restore_app", "/tmp/a.bak", ""),
        ("restore_app", "/tmp/b.bak", ""),
    ]


def test_save_shared_preserves_valid_json_across_repeated_updates(monkeypatch, tmp_path):
    _ = monkeypatch
    _ = tmp_path
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    store_path = data_dir() / "migration_shared.json"
    if store_path.exists():
        store_path.unlink()

    for idx in range(25):
        result = sdk_mod.save_shared({"key": f"k{idx}", "value": idx}, context=None)
        assert result.ok is True
        payload = json.loads(store_path.read_text(encoding="utf-8"))
        assert payload[f"k{idx}"] == idx


def test_save_shared_serializes_read_modify_write_to_prevent_lost_updates(monkeypatch, tmp_path):
    _ = monkeypatch
    _ = tmp_path
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    store_path = data_dir() / "migration_shared.json"
    if store_path.exists():
        store_path.unlink()

    start = threading.Barrier(3)

    def worker(key, value):
        start.wait()
        result = sdk_mod.save_shared({"key": key, "value": value}, context=None)
        assert result.ok is True

    t1 = threading.Thread(target=worker, args=("alpha", 1))
    t2 = threading.Thread(target=worker, args=("beta", 2))
    t1.start()
    t2.start()
    start.wait()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert not t1.is_alive()
    assert not t2.is_alive()

    payload = json.loads(store_path.read_text(encoding="utf-8"))
    assert payload["alpha"] == 1
    assert payload["beta"] == 2


def test_update_store_uses_cross_process_lock_to_prevent_lost_updates(tmp_path):
    _ = tmp_path
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    store_path = sdk_mod._shared_path()
    if store_path.exists():
        store_path.unlink()

    ctx = multiprocessing.get_context("spawn")
    first_ready = ctx.Event()
    release_first = ctx.Event()

    first = ctx.Process(
        target=_cross_process_update_worker,
        args=(first_ready, release_first, "alpha", 1),
    )
    second = ctx.Process(
        target=_cross_process_update_worker,
        args=(None, None, "beta", 2),
    )

    first.start()
    assert first_ready.wait(timeout=10)

    second.start()
    time.sleep(0.1)
    release_first.set()

    first.join(timeout=15)
    second.join(timeout=15)

    assert first.exitcode == 0
    assert second.exitcode == 0

    payload = json.loads(store_path.read_text(encoding="utf-8"))
    assert payload["alpha"] == 1
    assert payload["beta"] == 2
