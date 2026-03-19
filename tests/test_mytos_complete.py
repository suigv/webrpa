"""Tests for AndroidApiClient (30001 port) and mytos.* action registry.

Previously tested MytSdkClient methods that have been migrated to AndroidApiClient.
Now validates the correct 30001 paths per official MYTOS API documentation.
"""

import importlib
from pathlib import Path


def _load_android_api_client():
    return importlib.import_module("hardware_adapters.android_api_client")


def _load_myt_client_module():
    return importlib.import_module("hardware_adapters.myt_client")


def test_android_api_client_proxy_paths(monkeypatch):
    """AndroidApiClient uses correct 30001 paths per documentation."""
    mod = _load_android_api_client()
    base_mod = _load_myt_client_module()
    BaseHTTPClient = base_mod.BaseHTTPClient
    AndroidApiClient = mod.AndroidApiClient

    called: list[tuple[str, str, dict]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        called.append((method, path, query or {}))
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    client = AndroidApiClient("10.0.0.2", 30001)

    assert client.query_s5_proxy()["ok"] is True
    assert client.set_s5_proxy("1.1.1.1", 1080, "u", "p")["ok"] is True
    assert client.stop_s5_proxy()["ok"] is True
    assert client.set_s5_filter(["example.com"])["ok"] is True
    assert client.get_clipboard()["ok"] is True
    assert client.set_clipboard("abc")["ok"] is True

    paths = [(m, p) for m, p, _ in called]
    # Per documentation: proxy calls use /proxy with cmd param; filter uses POST
    assert ("GET", "/proxy") in paths
    assert ("POST", "/proxy") in paths
    assert ("GET", "/clipboard") in paths

    # Verify cmd params for proxy
    proxy_calls = [(m, p, q) for m, p, q in called if p == "/proxy"]
    cmds = [q.get("cmd") for _, _, q in proxy_calls]
    assert 2 in cmds  # set_s5_proxy
    assert 3 in cmds  # stop_s5_proxy
    assert 4 in cmds  # set_s5_filter


def test_registry_registers_new_ui_actions(monkeypatch):
    reg_mod = importlib.import_module("engine.action_registry")
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


def test_android_api_client_extended_paths(monkeypatch, tmp_path: Path):
    """AndroidApiClient extended methods use correct 30001 paths."""
    mod = _load_android_api_client()
    base_mod = _load_myt_client_module()
    BaseHTTPClient = base_mod.BaseHTTPClient
    AndroidApiClient = mod.AndroidApiClient

    called_json: list[tuple[str, str, dict]] = []
    called_bytes: list[tuple[str, str, dict]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        called_json.append((method, path, query or {}))
        return {"ok": True, "data": {"path": path}}

    def fake_request_bytes(self, method, path, query=None):
        called_bytes.append((method, path, query or {}))
        return {"ok": True, "data": b"bin"}

    def fake_post_multipart(self, path, fields=None, files=None, query=None):
        called_json.append(("POST", path, query or {}))
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    monkeypatch.setattr(BaseHTTPClient, "request_bytes", fake_request_bytes)
    monkeypatch.setattr(BaseHTTPClient, "post_multipart", fake_post_multipart)

    client = AndroidApiClient("10.0.0.2", 30001)

    local_download = tmp_path / "d.json"
    local_upload = tmp_path / "u.txt"
    local_upload.write_text("hello", encoding="utf-8")
    cert = tmp_path / "cert.pem"
    cert.write_text("pem", encoding="utf-8")

    assert client.download_file("/tmp/a.txt", str(local_download))["ok"] is True
    assert client.upload_file(str(local_upload), "/tmp/u.txt")["ok"] is True
    assert client.backup_app("com.demo")["ok"] is True
    assert client.restore_app("/tmp/demo.bak")["ok"] is True
    assert client.install_apks(["a.apk"])["ok"] is True
    assert client.screenshot()["ok"] is True
    assert client.screenshot(level=3)["ok"] is True
    assert client.get_version()["ok"] is True
    assert client.get_container_info()["ok"] is True
    assert client.receive_sms()["ok"] is True
    assert client.get_call_records()["ok"] is True
    assert client.refresh_location()["ok"] is True
    assert client.ip_geolocation("23.247.138.215")["ok"] is True
    assert client.query_adb_permission()["ok"] is True
    assert client.switch_adb_permission(True)["ok"] is True
    assert client.set_google_id("adid-1")["ok"] is True
    assert client.get_google_id()["ok"] is True
    assert client.install_magisk()["ok"] is True
    assert client.upload_google_cert(str(cert))["ok"] is True
    assert client.autoclick_action("down", x=120, y=240)["ok"] is True
    assert client.autoclick_action("keypress", code="KEYCODE_BACK")["ok"] is True
    assert client.camera_hot_start(True)["ok"] is True
    assert client.set_key_block(True)["ok"] is True
    assert client.add_contact("demo", "10086")["ok"] is True
    assert client.get_root_allowed_apps()["ok"] is True
    assert client.set_root_allowed_app("com.demo", True)["ok"] is True
    assert client.get_boot_apps()["ok"] is True
    assert client.set_language_country("en", "US")["ok"] is True
    assert client.set_device_fingerprint({"lac": "12345", "imei": "123"})["ok"] is True
    assert client.set_shake(enabled=True)["ok"] is True

    # Verify correct 30001 paths per documentation
    expected_paths = {
        ("GET", "/download"),
        ("POST", "/upload"),
        ("GET", "/backrestore"),
        ("GET", "/snapshot"),
        ("GET", "/queryversion"),
        ("GET", "/info"),
        ("POST", "/sms"),
        ("GET", "/callog"),
        ("GET", "/task"),
        ("GET", "/modifydev"),
        ("GET", "/adb"),
        ("GET", "/adid"),
        ("GET", "/modulemgr"),
        ("POST", "/uploadkeybox"),
        ("GET", "/autoclick"),
        ("GET", "/camera"),
        ("GET", "/disablekey"),
        ("GET", "/addcontact"),
        ("GET", "/appbootstart"),
    }
    called_paths = {(method, path) for method, path, _ in called_json} | {
        (method, path) for method, path, _ in called_bytes
    }
    assert expected_paths.issubset(called_paths)
    assert ("GET", "/", {"task": "snap", "level": 3}) in called_bytes
    assert ("GET", "/modifydev", {"cmd": 17, "shake": 1}) in called_json
    fingerprint_call = next(
        query
        for method, path, query in called_json
        if method == "GET" and path == "/modifydev" and query.get("cmd") == 7
    )
    assert '"lac": "12345"' in fingerprint_call["data"]
    assert '"imei": "123"' in fingerprint_call["data"]


def test_mytos_actions_registered(monkeypatch):
    """mytos.* actions are registered and proxy to AndroidApiClient."""
    reg_mod = importlib.import_module("engine.action_registry")
    ActionRegistry = reg_mod.ActionRegistry
    register_defaults = reg_mod.register_defaults
    reg = ActionRegistry()
    monkeypatch.setattr(reg_mod, "_registry", reg)
    register_defaults()

    mytos_actions = [
        "mytos.query_s5_proxy",
        "mytos.set_s5_proxy",
        "mytos.stop_s5_proxy",
        "mytos.get_clipboard",
        "mytos.set_clipboard",
        "mytos.screenshot",
        "mytos.snap_screenshot",
        "mytos.download_file",
        "mytos.upload_file",
        "mytos.set_language_country",
        "mytos.set_fingerprint",
        "mytos.set_shake",
        "mytos.refresh_location",
        "mytos.get_google_id",
        "mytos.install_magisk",
    ]
    for action in mytos_actions:
        assert reg.has(action), f"Missing action: {action}"
