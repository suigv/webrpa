from engine.runner import Runner


def test_mytos_device_setup_plugin_success(monkeypatch):
    from engine.actions import sdk_actions

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip
            self.sdk_port = sdk_port

        def query_adb_permission(self):
            return {"ok": True, "data": {"enabled": False}}

        def switch_adb_permission(self, enabled: bool):
            return {"ok": True, "data": {"enabled": enabled}}

        def set_language_country(self, language: str, country: str):
            return {"ok": True, "data": {"language": language, "country": country}}

        def get_app_bootstart_list(self):
            return {"ok": True, "data": {"items": []}}

        def set_app_bootstart(self, package: str, enabled: bool):
            return {"ok": True, "data": {"package": package, "enabled": enabled}}

        def get_root_allowed_apps(self):
            return {"ok": True, "data": {"items": []}}

        def set_root_allowed_app(self, package: str, allowed: bool):
            return {"ok": True, "data": {"package": package, "allowed": allowed}}

        def get_container_info(self):
            return {"ok": True, "data": {"container": "demo"}}

    monkeypatch.setattr(sdk_actions, "MytSdkClient", FakeClient)

    result = Runner().run(
        {
            "task": "mytos_device_setup",
            "device_ip": "192.168.1.2",
            "sdk_port": 8000,
            "package": "com.demo.app",
            "language": "en",
            "country": "US",
            "enable_app_bootstart": True,
            "allow_root": True,
        }
    )

    assert result["status"] == "success"
    assert "completed" in result.get("message", "")
