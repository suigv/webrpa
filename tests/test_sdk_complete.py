import importlib

from engine.models.runtime import ExecutionContext


def _load_myt_client_module():
    for name in ("hardware_adapters.myt_client", "hardware_adapters.myt_client"):
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
    assert sdk.switch_model("android-02", "", localModel="pixel")["ok"] is True
    assert sdk.change_ssh_password("", "pass123")["ok"] is True

    assert ("GET", "/info/device", None, None) in captured
    assert ("GET", "/info", None, None) in captured
    assert ("POST", "/android/start", {"name": "android-01"}, None) in captured
    assert (
        "POST",
        "/android/switchModel",
        {"name": "android-01", "modelId": "m1"},
        None,
    ) in captured
    assert (
        "POST",
        "/android/switchModel",
        {"name": "android-02", "localModel": "pixel"},
        None,
    ) in captured
    assert ("POST", "/link/ssh/changePwd", {"password": "pass123"}, None) in captured


def test_sdk_required_field_validation():
    mod = _load_myt_client_module()
    MytSdkClient = mod.MytSdkClient
    sdk = MytSdkClient("192.168.1.2", 8000)

    assert sdk.rename_android("", "new")["ok"] is False
    assert sdk.exec_android("android-01", "")["ok"] is False
    assert sdk.backup_model("android-01", "")["ok"] is False
    assert sdk.switch_model("android-01", "")["ok"] is False
    assert sdk.set_auth_password("abc", "xyz")["ok"] is False


def test_sdk_action_binding_uses_runtime_target_endpoint(monkeypatch):
    sdk_actions_module = importlib.import_module("engine.actions.sdk_actions")

    seen: dict[str, object] = {}

    class _FakeSdkClient:
        def __init__(self, device_ip, sdk_port=8000, timeout_seconds=30.0, retries=3):
            seen["device_ip"] = device_ip
            seen["sdk_port"] = sdk_port
            seen["timeout_seconds"] = timeout_seconds
            seen["retries"] = retries

        def switch_model(self, name, model_id="", **kwargs):
            seen["name"] = name
            seen["model_id"] = model_id
            seen["kwargs"] = kwargs
            return {"ok": True, "data": {"name": name, "model_id": model_id, "kwargs": kwargs}}

    monkeypatch.setattr(sdk_actions_module, "MytSdkClient", _FakeSdkClient)

    handler = sdk_actions_module.get_sdk_action_bindings()["sdk.switch_model"]
    result = handler(
        {"name": "android-12", "model_id": "229"},
        ExecutionContext(
            payload={},
            runtime={"target": {"device_ip": "192.168.1.214", "sdk_port": 8000}},
        ),
    )

    assert result.ok is True
    assert seen["device_ip"] == "192.168.1.214"
    assert seen["sdk_port"] == 8000
    assert seen["name"] == "android-12"
    assert seen["model_id"] == "229"


def test_sdk_documented_endpoint_calls(monkeypatch):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient
    calls: list[tuple[str, str, dict[str, object] | None, dict[str, object] | None]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        calls.append((method, path, payload, query))
        return {"ok": True, "data": {"path": path, "query": query}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    sdk = MytSdkClient("192.168.1.2", 8000)

    # MytSdkClient 8000 port only — these methods now live on AndroidApiClient
    assert sdk.get_device_info()["ok"] is True
    assert sdk.get_api_version()["ok"] is True
    assert sdk.list_androids()["ok"] is True

    assert ("GET", "/info/device", None, None) in calls
    assert ("GET", "/info", None, None) in calls
    assert ("GET", "/android", None, None) in calls


def test_sdk_box_endpoint_mapping_expanded(monkeypatch, tmp_path):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient
    calls: list[tuple[str, str, dict[str, object] | None, dict[str, object] | None]] = []

    def fake_request_json(self, method, path, payload=None, query=None):
        calls.append((method, path, payload, query))
        return {"ok": True, "data": {"path": path}}

    def fake_request_bytes(self, method, path, query=None):
        calls.append((method, path, None, query))
        return {"ok": True, "data": b"tar"}

    def fake_post_multipart(self, path, fields=None, files=None, query=None):
        calls.append(("POST", path, dict(fields or {}), dict(query or {})))
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    monkeypatch.setattr(BaseHTTPClient, "request_bytes", fake_request_bytes)
    monkeypatch.setattr(BaseHTTPClient, "post_multipart", fake_post_multipart)

    sdk = MytSdkClient("192.168.1.2", 8000)

    file_path = tmp_path / "package.tar"
    file_path.write_text("x", encoding="utf-8")

    assert (
        sdk.create_android({"name": "a-01", "imageUrl": "repo/a:v1", "dns": "223.5.5.5"})["ok"]
        is True
    )
    assert sdk.reset_android({"name": "a-01"})["ok"] is True
    assert sdk.delete_android("a-01")["ok"] is True
    assert sdk.delete_image("repo/a:v1")["ok"] is True
    assert sdk.list_image_tars()["ok"] is True
    assert sdk.delete_image_tar("a.tar")["ok"] is True
    assert sdk.export_image("repo/a:v1")["ok"] is True
    assert sdk.download_image_tar("a.tar", str(tmp_path / "a.tar"))["ok"] is True
    assert sdk.import_image(str(file_path))["ok"] is True
    assert sdk.export_android("a-01")["ok"] is True
    assert sdk.import_android(str(file_path))["ok"] is True
    assert sdk.list_phone_models_online()["ok"] is True
    assert sdk.list_country_codes()["ok"] is True
    assert sdk.set_android_macvlan({"name": "a-01", "mode": "on"})["ok"] is True
    assert sdk.list_myt_bridge()["ok"] is True
    assert sdk.create_myt_bridge({"name": "br0"})["ok"] is True
    assert sdk.open_ssh_terminal(username="root")["ok"] is True
    assert sdk.open_container_exec(name="a-01")["ok"] is True
    assert sdk.get_ssh_ws_url(username="root")["ok"] is True
    assert sdk.get_ssh_page_url(token="abc")["ok"] is True
    assert sdk.get_container_exec_page_url(name="a-01")["ok"] is True
    assert sdk.get_container_exec_ws_url(name="a-01")["ok"] is True
    assert sdk.list_vpc_groups()["ok"] is True
    assert sdk.list_local_phone_models()["ok"] is True
    assert sdk.upgrade_server()["ok"] is True
    assert sdk.get_server_network()["ok"] is True
    assert sdk.get_lm_info()["ok"] is True
    assert sdk.get_lm_models()["ok"] is True
    assert sdk.start_lm_server()["ok"] is True
    assert sdk.stop_lm_server()["ok"] is True

    assert (
        "POST",
        "/android",
        {"name": "a-01", "imageUrl": "repo/a:v1", "dns": "223.5.5.5"},
        None,
    ) in calls
    assert ("PUT", "/android", {"name": "a-01"}, None) in calls
    assert ("DELETE", "/android", {"name": "a-01"}, None) in calls
    assert ("DELETE", "/android/image", {"imageUrl": "repo/a:v1"}, None) in calls
    assert ("GET", "/android/imageTar", None, None) in calls
    assert ("DELETE", "/android/imageTar", {"filename": "a.tar"}, None) in calls
    assert ("POST", "/android/image/export", {"imageUrl": "repo/a:v1"}, None) in calls
    assert ("GET", "/android/image/download", None, {"filename": "a.tar"}) in calls
    assert ("POST", "/android/image/import", {}, {}) in calls
    assert ("POST", "/android/export", {"name": "a-01"}, None) in calls
    assert ("POST", "/android/import", {}, {}) in calls
    assert ("GET", "/android/phoneModel", None, None) in calls
    assert ("GET", "/android/countryCode", None, None) in calls
    assert ("POST", "/android/macvlan", {"name": "a-01", "mode": "on"}, None) in calls
    assert ("GET", "/mytBridge", None, None) in calls
    assert ("POST", "/mytBridge", {"name": "br0"}, None) in calls
    assert ("GET", "/link/ssh", None, {"username": "root"}) in calls
    assert ("GET", "/link/exec", None, {"name": "a-01"}) in calls
    assert ("GET", "/mytVpc/group", None, None) in calls
    assert ("GET", "/phoneModel", None, None) in calls
    assert ("GET", "/server/upgrade", None, None) in calls
    assert ("GET", "/server/network", None, None) in calls
    assert ("GET", "/lm/info", None, None) in calls
    assert ("GET", "/lm/models", None, None) in calls
    assert ("POST", "/lm/server/start", None, None) in calls
    assert ("POST", "/lm/server/stop", None, None) in calls

    assert sdk.get_ssh_ws_url(username="root")["data"]["url"].startswith(
        "ws://192.168.1.2:8000/link/ssh"
    )
    assert sdk.get_ssh_page_url(token="abc")["data"]["url"].startswith(
        "http://192.168.1.2:8000/ssh"
    )
    assert sdk.get_container_exec_page_url(name="a-01")["data"]["url"].startswith(
        "http://192.168.1.2:8000/container/exec"
    )
    assert sdk.get_container_exec_ws_url(name="a-01")["data"]["url"].startswith(
        "ws://192.168.1.2:8000/link/exec"
    )


def test_sdk_box_parameter_contracts(monkeypatch, tmp_path):
    mod = _load_myt_client_module()
    BaseHTTPClient = mod.BaseHTTPClient
    MytSdkClient = mod.MytSdkClient

    def fake_request_json(self, method, path, payload=None, query=None):
        return {
            "ok": True,
            "data": {"method": method, "path": path, "payload": payload, "query": query},
        }

    def fake_request_bytes(self, method, path, query=None):
        return {"ok": True, "data": b"bin"}

    def fake_post_multipart(self, path, fields=None, files=None, query=None):
        return {"ok": True, "data": {"path": path}}

    monkeypatch.setattr(BaseHTTPClient, "request_json", fake_request_json)
    monkeypatch.setattr(BaseHTTPClient, "request_bytes", fake_request_bytes)
    monkeypatch.setattr(BaseHTTPClient, "post_multipart", fake_post_multipart)

    sdk = MytSdkClient("192.168.1.2", 8000)

    assert sdk.create_android({"name": "a-01", "dns": "223.5.5.5"})["ok"] is False
    assert sdk.create_android({"imageUrl": "repo/a:v1", "dns": "223.5.5.5"})["ok"] is False
    assert sdk.reset_android({"name": ""})["ok"] is False
    assert sdk.delete_android("")["ok"] is False
    assert sdk.delete_image("")["ok"] is False
    assert sdk.delete_image_tar("")["ok"] is False
    assert sdk.export_image("")["ok"] is False
    assert sdk.download_image_tar("", str(tmp_path / "a.tar"))["ok"] is False
    assert sdk.download_image_tar("a.tar", "")["ok"] is False
    assert sdk.import_image(str(tmp_path / "missing.tar"))["ok"] is False
    assert sdk.import_android(str(tmp_path / "missing_android.tar"))["ok"] is False
    assert sdk.set_android_macvlan({"name": ""})["ok"] is False
    assert sdk.delete_backup("")["ok"] is False
    assert sdk.download_backup("", str(tmp_path / "backup.tar"))["ok"] is False
    assert sdk.delete_model_backup("")["ok"] is False
    assert sdk.import_model(str(tmp_path / "missing_model.zip"))["ok"] is False
    assert sdk.switch_model("android-01", "")["ok"] is False
    assert sdk.switch_model("android-01", "", localModel="pixel")["ok"] is True
    assert sdk.change_ssh_password("", "")["ok"] is False
    assert sdk.delete_myt_bridge("")["ok"] is False
    assert sdk.delete_local_phone_model("")["ok"] is False
    assert sdk.export_local_phone_model("")["ok"] is False
    assert sdk.import_phone_model(str(tmp_path / "missing_phone_model.zip"))["ok"] is False
    assert sdk.upload_server_upgrade(str(tmp_path / "missing_upgrade.zip"))["ok"] is False
    assert sdk.switch_docker_api(True)["ok"] is True
    assert sdk.import_lm_package(str(tmp_path / "missing_lm.zip"))["ok"] is False
    assert sdk.delete_lm_local("")["ok"] is False
    assert sdk.set_lm_work_mode("")["ok"] is False
