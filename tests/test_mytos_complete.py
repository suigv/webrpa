import importlib
from pathlib import Path


def _load_action_registry_module():
    for name in ("engine.action_registry", "engine.action_registry"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import action_registry module")


def _load_myt_client_module():
    for name in ("hardware_adapters.myt_client", "hardware_adapters.myt_client"):
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
    assert sdk.set_s5_filter({"domains": ["x.com"]})["ok"] is True
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
        return {"ok": True, "data": {"path": path}}

    def fake_request_bytes(self, method, path, query=None):
        called.append((method, path))
        return {"ok": True, "data": b"bin"}

    def fake_post_multipart(self, path, fields=None, files=None, query=None):
        called.append(("POST", path))
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    monkeypatch.setattr(BaseHTTPClient, "request_bytes", fake_request_bytes)
    monkeypatch.setattr(BaseHTTPClient, "post_multipart", fake_post_multipart)

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
    assert sdk.backup_app_info("com.demo", "/tmp/demo.bak")["ok"] is True
    assert sdk.restore_app_info("/tmp/demo.bak")["ok"] is True
    assert sdk.batch_install_apps(["a.apk"])["ok"] is True
    assert sdk.mytos_screenshot()["ok"] is True
    assert sdk.get_version()["ok"] is True
    assert sdk.get_container_info()["ok"] is True
    assert sdk.receive_sms()["ok"] is True
    assert sdk.get_call_records()["ok"] is True
    assert sdk.refresh_location()["ok"] is True
    assert sdk.ip_geolocation("23.247.138.215", "en")["ok"] is True
    assert sdk.query_adb_permission()["ok"] is True
    assert sdk.switch_adb_permission(True)["ok"] is True
    assert sdk.set_google_id("adid-1")["ok"] is True
    assert sdk.get_google_id()["ok"] is True
    assert sdk.module_manager("check", "magisk")["ok"] is True
    assert sdk.install_magisk()["ok"] is True
    cert = tmp_path / "cert.pem"
    cert.write_text("pem", encoding="utf-8")
    assert sdk.upload_google_cert(str(cert))["ok"] is True
    backup = tmp_path / "backup.zip"
    backup.write_text("zip", encoding="utf-8")
    assert sdk.export_app_data("com.demo")["ok"] is True
    assert sdk.import_app_data("com.demo", str(backup))["ok"] is True
    assert sdk.auto_click(action="down", finger_id=1, x=120, y=240)["ok"] is True
    assert sdk.auto_click(action="keypress", code="KEYCODE_BACK")["ok"] is True
    assert sdk.camera_hot_start(True, "/sdcard/DCIM/Camera/hot.mp4")["ok"] is True
    assert sdk.query_background_keepalive()["ok"] is True
    assert sdk.add_background_keepalive("com.demo.keepalive")["ok"] is True
    assert sdk.update_background_keepalive("com.demo.keepalive")["ok"] is True
    assert sdk.remove_background_keepalive("com.demo.keepalive")["ok"] is True
    assert sdk.set_key_block(enabled=True)["ok"] is True
    assert sdk.add_contact(contacts=[{"user": "demo", "tel": "10086"}])["ok"] is True
    assert sdk.get_root_allowed_apps()["ok"] is True
    assert sdk.set_root_allowed_app("com.demo", True)["ok"] is True
    assert sdk.set_virtual_camera_source(path="/sdcard/cam.mp4", type="video", resolution="1280x720")["ok"] is True
    assert sdk.get_app_bootstart_list()["ok"] is True
    assert sdk.set_app_bootstart(packages=["com.demo", "com.demo.second"])["ok"] is True
    assert sdk.set_language_country("en", "US")["ok"] is True
    assert sdk.get_webrtc_player_url(2)["ok"] is True
    assert sdk.import_model(str(import_zip))["ok"] is True
    assert sdk.list_models()["ok"] is True

    expected = {
        ("GET", "/download"),
        ("POST", "/upload"),
        ("POST", "/app/exportInfo"),
        ("POST", "/app/importInfo"),
        ("GET", "/backrestore"),
        ("POST", "/app/batchInstall"),
        ("GET", "/device/screenshot"),
        ("GET", "/device/version"),
        ("GET", "/device/container"),
        ("POST", "/sms/receive"),
        ("GET", "/call/records"),
        ("POST", "/location/refresh"),
        ("GET", "/location/ip"),
        ("GET", "/system/adb"),
        ("POST", "/system/adb"),
        ("POST", "/identity/googleId"),
        ("GET", "/identity/googleId"),
        ("POST", "/system/module"),
        ("POST", "/uploadkeybox"),
        ("POST", "/autoclick"),
        ("POST", "/camera"),
        ("POST", "/background"),
        ("POST", "/disablekey"),
        ("POST", "/addcontact"),
        ("GET", "/modifydev"),
        ("GET", "/appbootstart"),
        ("POST", "/appbootstart"),
        ("POST", "/android/backup/modelImport"),
        ("GET", "/lm/local"),
    }
    assert expected.issubset(set(called))
    webrtc = sdk.get_webrtc_player_url(2)["data"]
    assert "shost=10.0.0.2" in webrtc["url"]
    assert "sport=30107" in webrtc["url"]
    assert "rtc_p=30108" in webrtc["url"]
