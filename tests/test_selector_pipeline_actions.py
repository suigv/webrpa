import importlib
from types import SimpleNamespace


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


def _load_action_registry_module():
    for name in ("engine.action_registry", "engine.action_registry"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import action_registry module")


class _RpcBase:
    def init(self, ip, port, timeout):
        return True

    def close(self):
        return None

    def create_selector(self):
        return 1

    def addQuery_Text(self, selector, value):
        return True

    def addQuery_Id(self, selector, value):
        return True

    def addQuery_Desc(self, selector, value):
        return True

    def clear_selector(self, selector):
        return True


class FakeRpcHasNode(_RpcBase):
    def execQueryOne(self, selector):
        return SimpleNamespace(id="n1", text="hello")

    def execQueryAll(self, selector):
        return [SimpleNamespace(id="n1", text="hello")]


class FakeRpcNoNode(_RpcBase):
    def execQueryOne(self, selector):
        return None

    def execQueryAll(self, selector):
        return None


def test_selector_query_success(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcHasNode)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    result = ui_actions.create_selector({}, ctx)
    assert result.ok is True
    selector = ctx.vars["selector"]
    assert selector.addQuery_Text("hello") is True
    assert selector.addQuery_Id("id_demo") is True
    assert selector.addQuery_Desc("desc_demo") is True
    one = selector.execQueryOne()
    all_nodes = selector.execQueryAll()
    assert one.ok is True
    assert all_nodes.ok is True
    assert "node" in one.data
    assert "nodes" in all_nodes.data


def test_selector_query_not_found(monkeypatch):
    ui_actions = _load_ui_actions_module()
    reg_mod = _load_action_registry_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcNoNode)
    reg = reg_mod.ActionRegistry()
    monkeypatch.setattr(reg_mod, "_registry", reg)
    reg_mod.register_defaults()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    assert reg.resolve("ui.create_selector")({}, ctx).ok is True
    one = reg.resolve("ui.selector_exec_one")({}, ctx)
    all_nodes = reg.resolve("ui.selector_exec_all")({}, ctx)
    assert one.ok is False
    assert one.code == "not_found"
    assert all_nodes.ok is False
    assert all_nodes.code == "not_found"


def test_selector_runtime_actions_registered_and_work(monkeypatch):
    ui_actions = _load_ui_actions_module()
    reg_mod = _load_action_registry_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcHasNode)
    reg = reg_mod.ActionRegistry()
    monkeypatch.setattr(reg_mod, "_registry", reg)
    reg_mod.register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})
    assert reg.resolve("ui.create_selector")({}, ctx).ok is True
    assert reg.resolve("ui.selector_add_query")({"type": "text", "value": "hello"}, ctx).ok is True
    one = reg.resolve("ui.selector_exec_one")({}, ctx)
    all_nodes = reg.resolve("ui.selector_exec_all")({}, ctx)
    clear = reg.resolve("ui.selector_clear")({}, ctx)
    assert one.ok is True
    assert all_nodes.ok is True
    assert clear.ok is True
