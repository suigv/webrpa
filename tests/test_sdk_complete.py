import importlib


def _load_myt_client_module():
    for name in ("new.hardware_adapters.myt_client", "hardware_adapters.myt_client"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import myt_client module")


def test_http_client_failure_safe_invalid_host():
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    client = BaseHTTPClient("127.0.0.1", 1, timeout_seconds=0.01, retries=1)
    result = client.get("/health")
    assert result["ok"] is False
    assert "error" in result


def test_sdk_core_endpoint_mapping(monkeypatch):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient
    captured: list[tuple[str, str, dict[str, object] | None, dict[str, object] | None]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        captured.append((method, path, payload, query))
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    sdk = MytSdkClient("192.168.1.2", 8000)

    assert sdk.get_device_info()["ok"] is True
    assert sdk.get_api_version()["ok"] is True
    assert sdk.start_android("android-01")["ok"] is True
    assert sdk.switch_model("android-01", "m1")["ok"] is True
    assert sdk.query_s5_proxy()["ok"] is True
    assert sdk.set_clipboard("hello")["ok"] is True

    assert ("GET", "/info/device", None, None) in captured
    assert ("GET", "/info", None, None) in captured
    assert ("POST", "/android/start", {"name": "android-01"}, None) in captured
    assert ("POST", "/android/switchModel", {"name": "android-01", "modelId": "m1"}, None) in captured
    assert ("GET", "/proxy/status", None, None) in captured
    assert ("POST", "/clipboard", {"content": "hello"}, None) in captured


def test_sdk_required_field_validation():
    mod = _load_myt_client_module()
    MytSdkClient = mod.MytSdkClient
    sdk = MytSdkClient("192.168.1.2", 8000)

    assert sdk.rename_android("", "new")["ok"] is False
    assert sdk.exec_android("android-01", "")["ok"] is False
    assert sdk.backup_model("android-01", "")["ok"] is False
    assert sdk.set_auth_password("abc", "xyz")["ok"] is False
    assert sdk.set_s5_proxy({"ip": "1.1.1.1"})["ok"] is False
    assert sdk.ip_geolocation("")["ok"] is False


def test_sdk_fallback_endpoint_calls(monkeypatch):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient
    calls: list[tuple[str, str, dict[str, object] | None, dict[str, object] | None]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        calls.append((method, path, payload, query))
        if path in {"/proxy/status", "/device/version", "/identity/googleId", "/location/ip"}:
            return {"ok": False, "error": "missing"}
        return {"ok": True, "data": {"path": path, "query": query}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    sdk = MytSdkClient("192.168.1.2", 8000)

    assert sdk.query_s5_proxy()["ok"] is True
    assert sdk.get_version()["ok"] is True
    assert sdk.get_google_id()["ok"] is True
    assert sdk.ip_geolocation("23.247.138.215", "en")["ok"] is True

    assert ("GET", "/proxy", None, None) in calls
    assert ("GET", "/queryversion", None, None) in calls
    assert ("GET", "/adid", None, {"cmd": 2}) in calls
    assert ("GET", "/modifydev", None, {"cmd": 11, "ip": "23.247.138.215", "launage": "en"}) in calls
