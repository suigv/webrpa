import importlib
import json
import multiprocessing
import os
import threading
import time


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
    root_path_raw: str,
    ready_event,
    release_event,
    key: str,
    value: int,
) -> None:
    os.environ["MYT_NEW_ROOT"] = root_path_raw
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

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip
            self.sdk_port = sdk_port

        def get_device_info(self):
            return {"ok": True, "data": {"ip": self.device_ip, "port": self.sdk_port}}

        def set_clipboard(self, content: str):
            return {"ok": True, "data": {"content": content}}

        def ip_geolocation(self, ip: str, language: str = ""):
            return {"ok": True, "data": {"ip": ip, "language": language}}

    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    monkeypatch.setattr(sdk_mod, "MytSdkClient", FakeClient)

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.8", "sdk_port": 8010})
    res1 = reg.resolve("sdk.get_device_info")({}, ctx)
    assert res1.ok is True
    assert res1.data["result"]["data"]["ip"] == "192.168.1.8"

    res2 = reg.resolve("mytos.set_clipboard")({"content": "abc"}, ctx)
    assert res2.ok is True
    assert res2.data["result"]["data"]["content"] == "abc"

    res3 = reg.resolve("mytos.ip_geolocation")({"ip": "23.247.138.215", "language": "en"}, ctx)
    assert res3.ok is True
    assert res3.data["result"]["data"]["ip"] == "23.247.138.215"


def test_save_shared_preserves_valid_json_across_repeated_updates(monkeypatch, tmp_path):
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    monkeypatch.setattr(sdk_mod, "_resolve_root_path", lambda: str(tmp_path))

    for idx in range(25):
        result = sdk_mod.save_shared({"key": f"k{idx}", "value": idx}, context=None)
        assert result.ok is True
        payload = json.loads((tmp_path / "config" / "data" / "migration_shared.json").read_text(encoding="utf-8"))
        assert payload[f"k{idx}"] == idx


def test_save_shared_serializes_read_modify_write_to_prevent_lost_updates(monkeypatch, tmp_path):
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    monkeypatch.setattr(sdk_mod, "_resolve_root_path", lambda: str(tmp_path))

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

    payload = json.loads((tmp_path / "config" / "data" / "migration_shared.json").read_text(encoding="utf-8"))
    assert payload["alpha"] == 1
    assert payload["beta"] == 2


def test_update_store_uses_cross_process_lock_to_prevent_lost_updates(tmp_path):
    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    original_env = os.environ.get("MYT_NEW_ROOT")
    os.environ["MYT_NEW_ROOT"] = str(tmp_path)
    try:
        store_path = sdk_mod._shared_path()

        ctx = multiprocessing.get_context("spawn")
        first_ready = ctx.Event()
        release_first = ctx.Event()

        first = ctx.Process(
            target=_cross_process_update_worker,
            args=(str(tmp_path), first_ready, release_first, "alpha", 1),
        )
        second = ctx.Process(
            target=_cross_process_update_worker,
            args=(str(tmp_path), None, None, "beta", 2),
        )

        first.start()
        assert first_ready.wait(timeout=2)

        second.start()
        time.sleep(0.1)
        release_first.set()

        first.join(timeout=5)
        second.join(timeout=5)

        assert first.exitcode == 0
        assert second.exitcode == 0

        payload = json.loads(store_path.read_text(encoding="utf-8"))
        assert payload["alpha"] == 1
        assert payload["beta"] == 2
    finally:
        if original_env is None:
            os.environ.pop("MYT_NEW_ROOT", None)
        else:
            os.environ["MYT_NEW_ROOT"] = original_env
