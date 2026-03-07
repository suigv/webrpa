from engine.runner import Runner


def test_device_reboot_waits_until_running(monkeypatch):
    from engine.actions import sdk_actions

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.statuses = ["stopped", "booting", "running"]

        def restart_android(self, name: str):
            return {"ok": True, "data": {"name": name}}

        def get_cloud_status(self, name: str):
            status = self.statuses.pop(0)
            return {"ok": True, "data": {"name": name, "status": status}}

    monkeypatch.setattr(sdk_actions, "MytSdkClient", FakeClient)

    result = Runner().run({"task": "device_reboot", "device_ip": "192.168.1.2", "name": "android-01"})

    assert result["task"] == "device_reboot"
    assert result["status"] == "success"
    assert "completed" in result["message"]


def test_device_soft_reset_runs_cleanup_and_waits_until_running(monkeypatch):
    from engine.actions import sdk_actions, ui_actions

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.statuses = ["restarting", "running"]

        def restart_android(self, name: str):
            return {"ok": True, "data": {"name": name}}

        def get_cloud_status(self, name: str):
            status = self.statuses.pop(0)
            return {"ok": True, "data": {"name": name, "status": status}}

    class FakeRpc:
        def __init__(self):
            self.commands: list[str] = []

        def stopApp(self, package: str):
            return True

        def keyPress(self, key_code: int):
            return True

        def exec_cmd(self, command: str):
            self.commands.append(command)
            return ("ok", True)

    rpc = FakeRpc()

    monkeypatch.setattr(sdk_actions, "MytSdkClient", FakeClient)
    monkeypatch.setattr(ui_actions, "_get_rpc", lambda params, context: (rpc, None))
    monkeypatch.setattr(ui_actions, "_close_rpc", lambda rpc_obj: None)

    result = Runner().run(
        {
            "task": "device_soft_reset",
            "device_ip": "192.168.1.2",
            "name": "android-01",
            "package": "com.twitter.android",
        }
    )

    assert result["task"] == "device_soft_reset"
    assert result["status"] == "success"
    assert any(cmd == "am force-stop com.twitter.android" for cmd in rpc.commands)
    assert any(cmd == "pm clear com.twitter.android" for cmd in rpc.commands)

