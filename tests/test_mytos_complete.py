import importlib
from pathlib import Path


def _load_action_registry_module():
    for name in ("new.engine.action_registry", "engine.action_registry"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import action_registry module")


def _load_myt_client_module():
    for name in ("new.hardware_adapters.myt_client", "hardware_adapters.myt_client"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import myt_client module")


def test_mytos_api_method_mapping(monkeypatch):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient
    called: list[tuple[str, str]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        called.append((method, path))
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    sdk = MytSdkClient("10.0.0.2", 8000)

    assert sdk.query_s5_proxy()["ok"] is True
    assert sdk.set_s5_proxy({"s5IP": "1.1.1.1", "s5Port": 1080, "s5User": "u", "s5Password": "p"})["ok"] is True
    assert sdk.stop_s5_proxy()["ok"] is True
    assert sdk.set_s5_filter({"allow": ["x.com"]})["ok"] is True
    assert sdk.get_clipboard()["ok"] is True
    assert sdk.set_clipboard("abc")["ok"] is True

    assert ("GET", "/proxy/status") in called
    assert ("POST", "/proxy/set") in called
    assert ("POST", "/proxy/stop") in called
    assert ("POST", "/proxy/filter") in called
    assert ("GET", "/clipboard") in called
    assert ("POST", "/clipboard") in called


def test_registry_registers_new_ui_actions(monkeypatch):
    reg_mod = _load_action_registry_module()
    ActionRegistry = reg_mod.ActionRegistry
    register_defaults = reg_mod.register_defaults
    reg = ActionRegistry()
    monkeypatch.setattr(reg_mod, "_registry", reg)
    register_defaults()
    assert reg.has("ui.click")
    assert reg.has("ui.input_text")
    assert reg.has("ui.swipe")
    assert reg.has("ui.key_press")
    assert reg.has("app.open")
    assert reg.has("app.stop")


def test_mytos_extended_api_method_mapping(monkeypatch, tmp_path: Path):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient

    called: list[tuple[str, str]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        called.append((method, path))
        if path == "/download":
            return {"ok": True, "data": {"content": "x"}}
        if path == "/lm/local":
            return {"ok": False, "error": "missing"}
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)

    sdk = MytSdkClient("10.0.0.2", 8000)

    local_download = tmp_path / "d.json"
    local_upload = tmp_path / "u.txt"
    local_upload.write_text("hello", encoding="utf-8")
    import_zip = tmp_path / "model.zip"
    import_zip.write_text("zip", encoding="utf-8")

    assert sdk.download_file("/tmp/a.txt", str(local_download))["ok"] is True
    assert sdk.upload_file(str(local_upload), "/tmp/u.txt")["ok"] is True
    assert sdk.export_app_info("com.demo")["ok"] is True
    assert sdk.import_app_info("com.demo", {"k": "v"})["ok"] is True
    assert sdk.batch_install_apps(["a.apk"])["ok"] is True
    assert sdk.mytos_screenshot()["ok"] is True
    assert sdk.get_version()["ok"] is True
    assert sdk.get_container_info()["ok"] is True
    assert sdk.receive_sms()["ok"] is True
    assert sdk.get_call_records()["ok"] is True
    assert sdk.refresh_location()["ok"] is True
    assert sdk.ip_geolocation("23.247.138.215", "en")["ok"] is True
    assert sdk.switch_adb_permission(True)["ok"] is True
    assert sdk.get_google_id()["ok"] is True
    assert sdk.install_magisk()["ok"] is True
    assert sdk.import_model(str(import_zip))["ok"] is True
    assert sdk.list_models()["ok"] is True

    expected = {
        ("GET", "/download"),
        ("POST", "/upload"),
        ("POST", "/app/exportInfo"),
        ("POST", "/app/importInfo"),
        ("POST", "/app/batchInstall"),
        ("GET", "/device/screenshot"),
        ("GET", "/device/version"),
        ("GET", "/device/container"),
        ("POST", "/sms/receive"),
        ("GET", "/call/records"),
        ("POST", "/location/refresh"),
        ("GET", "/location/ip"),
        ("POST", "/system/adb"),
        ("GET", "/identity/googleId"),
        ("POST", "/system/magisk/install"),
        ("POST", "/android/backup/modelImport"),
        ("GET", "/lm/local"),
        ("GET", "/models"),
    }
    assert expected.issubset(set(called))
