from engine.runner import Runner


def test_hezi_sdk_probe_plugin_success(monkeypatch):
    from engine.actions import sdk_actions

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip
            self.sdk_port = sdk_port

        def get_api_version(self):
            return {"ok": True, "data": {"version": "1.0.0"}}

        def get_device_info(self):
            return {"ok": True, "data": {"device_ip": self.device_ip}}

        def get_server_network(self):
            return {"ok": True, "data": {"interfaces": []}}

        def list_androids(self, **query):
            return {"ok": True, "data": {"items": [], "query": query}}

        def list_backups(self, name: str = ""):
            return {"ok": True, "data": {"items": [], "name": name}}

        def list_vpc_groups(self):
            return {"ok": True, "data": {"items": []}}

        def list_local_phone_models(self):
            return {"ok": True, "data": {"items": []}}

        def get_cloud_status(self, name: str):
            return {"ok": True, "data": {"name": name, "status": "running"}}

    monkeypatch.setattr(sdk_actions, "MytSdkClient", FakeClient)

    result = Runner().run(
        {
            "task": "hezi_sdk_probe",
            "device_ip": "192.168.1.2",
            "sdk_port": 8000,
            "android_name": "android-01",
        }
    )

    assert result["task"] == "hezi_sdk_probe"
    assert result["status"] == "success"
    assert "probe completed" in result.get("message", "")
