import importlib


def _load_ui_actions_module():
    for name in ("engine.actions.ui_actions", "engine.actions.ui_actions"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import ui_actions module")


def _load_execution_context():
    for name in ("engine.models.runtime", "engine.models.runtime"):
        try:
            return importlib.import_module(name).ExecutionContext
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import ExecutionContext")


class FakeRpcOK:
    def init(self, ip, port, timeout) -> bool:
        return True

    def close(self) -> None:
        return None

    def openApp(self, package) -> bool:
        return True

    def exec_cmd(self, command) -> tuple[str, bool]:
        if command.startswith("pidof"):
            return ("1234", True)
        return ("ok", True)

    def keyPress(self, code) -> bool:
        return True


class FakeRpcTimeout(FakeRpcOK):
    def openApp(self, package) -> bool:
        return False

    def exec_cmd(self, command) -> tuple[str, bool]:
        return ("", False)


def test_app_ensure_running_happy_path(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcOK)
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2}
    )

    result = ui_actions.app_ensure_running({"package": "com.demo.app"}, ctx)
    assert result.ok is True
    assert result.code == "ok"


def test_app_ensure_running_timeout(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcTimeout)
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2}
    )

    result = ui_actions.app_ensure_running({"package": "com.demo.app", "verify_timeout": 0.1}, ctx)
    assert result.ok is False
    assert result.code == "timeout"


def test_app_grant_and_dismiss(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcOK)
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2}
    )

    grant = ui_actions.app_grant_permissions(
        {"package": "com.demo.app", "permissions": ["android.permission.CAMERA"]}, ctx
    )
    assert grant.ok is True
    dismiss = ui_actions.app_dismiss_popups({"back_presses": 2, "delay_ms": 10}, ctx)
    assert dismiss.ok is True
