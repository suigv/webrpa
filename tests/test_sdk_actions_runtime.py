import importlib


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
