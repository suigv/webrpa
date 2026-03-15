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
    def init(self, ip, port, timeout) -> bool:
        _ = (ip, port, timeout)
        connected = True
        return connected

    def close(self):
        return None

    def create_selector(self):
        return 1

    def addQuery_Text(self, selector, value):
        return True

    def addQuery_TextStartWith(self, selector, value):
        return True

    def addQuery_TextEndWith(self, selector, value):
        return True

    def addQuery_TextMatchWith(self, selector, value):
        return True

    def addQuery_TextContain(self, selector, value):
        return True

    def addQuery_Id(self, selector, value):
        return True

    def addQuery_IdStartWith(self, selector, value):
        return True

    def addQuery_IdEndWith(self, selector, value):
        return True

    def addQuery_IdContainWith(self, selector, value):
        return True

    def addQuery_IdMatchWith(self, selector, value):
        return True

    def addQuery_Class(self, selector, value):
        return True

    def addQuery_ClassStartWith(self, selector, value):
        return True

    def addQuery_ClassEndWith(self, selector, value):
        return True

    def addQuery_ClassContainWith(self, selector, value):
        return True

    def addQuery_ClassMatchWith(self, selector, value):
        return True

    def addQuery_Desc(self, selector, value):
        return True

    def addQuery_DescStartWith(self, selector, value):
        return True

    def addQuery_DescEndWith(self, selector, value):
        return True

    def addQuery_DescContainWith(self, selector, value):
        return True

    def addQuery_DescMatchWith(self, selector, value):
        return True

    def addQuery_Package(self, selector, value):
        return True

    def addQuery_PackageStartWith(self, selector, value):
        return True

    def addQuery_PackageEndWith(self, selector, value):
        return True

    def addQuery_PackageContainWith(self, selector, value):
        return True

    def addQuery_PackageMatchWith(self, selector, value):
        return True

    def addQuery_Bounds(self, selector, left, top, right, bottom):
        return True

    def addQuery_BoundsInside(self, selector, left, top, right, bottom):
        return True

    def addQuery_Clickable(self, selector, enabled):
        return True

    def addQuery_Enable(self, selector, enabled):
        return True

    def addQuery_Index(self, selector, index):
        return True

    def clear_selector(self, selector):
        return True

    def free_selector(self, selector):
        return True

    def find_nodes(self, selector, max_cnt_ret, timeout_ms):
        _ = (selector, max_cnt_ret, timeout_ms)
        return 101

    def get_nodes_size(self, nodes):
        _ = nodes
        return 2

    def get_node_by_index(self, nodes, index):
        _ = nodes
        return 200 + int(index)

    def free_nodes(self, nodes):
        _ = nodes
        return True

    def get_node_parent(self, node):
        return int(node) + 1000

    def get_node_child_count(self, node):
        _ = node
        return 3

    def get_node_child(self, node, index):
        return int(node) + int(index) + 1

    def get_node_text(self, node):
        return f"text-{node}"

    def get_node_id(self, node):
        return f"id-{node}"

    def get_node_class(self, node):
        return "class-demo"

    def get_node_package(self, node):
        return "pkg.demo"

    def get_node_desc(self, node):
        return f"desc-{node}"

    def get_node_bound(self, node):
        _ = node
        return {"left": 1, "top": 2, "right": 3, "bottom": 4}

    def get_node_bound_center(self, node):
        _ = node
        return {"x": 2, "y": 3}

    def get_node_json(self, node):
        return f'{{"node": {int(node)}}}'

    def click_node(self, node):
        _ = node
        return bool(True)

    def long_click_node(self, node):
        _ = node
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


def test_selector_add_query_extended_modes(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcHasNode)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    assert ui_actions.create_selector({}, ctx).ok is True
    assert ui_actions.selector_add_query({"type": "class", "mode": "contains", "value": "btn"}, ctx).ok is True
    assert ui_actions.selector_add_query({"type": "package", "mode": "start_with", "value": "com.demo"}, ctx).ok is True
    assert ui_actions.selector_add_query({"type": "bounds", "left": 1, "top": 2, "right": 3, "bottom": 4}, ctx).ok is True
    assert ui_actions.selector_add_query({"type": "clickable", "enabled": True}, ctx).ok is True
    assert ui_actions.selector_add_query({"type": "index", "index": 2}, ctx).ok is True


def test_selector_node_collection_actions(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcHasNode)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    assert ui_actions.create_selector({}, ctx).ok is True
    find_res = ui_actions.selector_find_nodes({"max_count": 10, "timeout_ms": 500, "save_as": "nodes_h"}, ctx)
    assert find_res.ok is True
    assert ctx.vars["nodes_h"] == 101

    size_res = ui_actions.selector_get_nodes_size({"nodes_var": "nodes_h"}, ctx)
    assert size_res.ok is True
    assert size_res.data["count"] == 2

    node_res = ui_actions.selector_get_node_by_index({"nodes_var": "nodes_h", "index": 1, "save_as": "node_h"}, ctx)
    assert node_res.ok is True
    assert ctx.vars["node_h"] == 201

    parent_res = ui_actions.node_get_parent({"node_var": "node_h", "save_as": "parent_h"}, ctx)
    assert parent_res.ok is True
    assert ctx.vars["parent_h"] == 1201

    child_count_res = ui_actions.node_get_child_count({"node_var": "node_h"}, ctx)
    assert child_count_res.ok is True
    assert child_count_res.data["count"] == 3

    child_res = ui_actions.node_get_child({"node_var": "node_h", "index": 0, "save_as": "child_h"}, ctx)
    assert child_res.ok is True
    assert ctx.vars["child_h"] == 202

    free_res = ui_actions.selector_free_nodes({"nodes_var": "nodes_h"}, ctx)
    assert free_res.ok is True
    assert "nodes_h" not in ctx.vars


def test_selector_replace_frees_previous_before_close(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})
    events = []

    class RecordingRpc(_RpcBase):
        def __init__(self):
            self.name = f"rpc-{len([entry for entry in events if entry[0] == 'create_rpc'])}"
            events.append(("create_rpc", self.name))

        def close(self):
            events.append(("close", self.name))
            return None

    original_selector_cls = ui_actions.MytSelector

    class RecordingSelector(original_selector_cls):
        def clear_selector(self):
            events.append(("clear", self.rpc.name))
            return True

        def free_selector(self):
            events.append(("free", self.rpc.name))
            return True

    monkeypatch.setattr(ui_actions, "MytRpc", RecordingRpc)
    monkeypatch.setattr(ui_actions, "MytSelector", RecordingSelector)

    first = ui_actions.create_selector({}, ctx)
    second = ui_actions.create_selector({}, ctx)

    assert first.ok is True
    assert second.ok is True
    assert [entry for entry in events if entry[1] == "rpc-0"] == [
        ("create_rpc", "rpc-0"),
        ("clear", "rpc-0"),
        ("free", "rpc-0"),
        ("close", "rpc-0"),
    ]



def test_selector_click_one_always_tears_down_before_close(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    class RecordingRpc(_RpcBase):
        def __init__(self, events, click_ok=True):
            self.events = events
            self.click_ok = click_ok

        def execQueryOne(self, selector):
            _ = selector
            return 101

        def touchDown(self, finger_id, x, y):
            self.events.append("click")
            return self.click_ok

        def touchUp(self, finger_id, x, y):
            return self.click_ok

        def click_node(self, node):
            _ = node
            self.events.append("click_node")
            return self.click_ok

        def close(self):
            self.events.append("close")
            return None

    cases = [
        ({"type": "text", "value": "hello"}, "ok", True),
        ({}, "invalid_params", True),
        ({"type": "text", "value": "hello"}, "click_failed", False),
    ]

    original_selector_cls = ui_actions.MytSelector

    for params, expected_code, click_ok in cases:
        events = []
        rpc = RecordingRpc(events, click_ok=click_ok)

        class RecordingSelector(original_selector_cls):
            def clear_selector(self):
                events.append("clear")
                return True

            def free_selector(self):
                events.append("free")
                return True

        monkeypatch.setattr(ui_actions, "MytSelector", RecordingSelector)
        monkeypatch.setattr(ui_actions, "_get_rpc", lambda params, context, rpc=rpc: (rpc, None))

        result = ui_actions.selector_click_one(params, ctx)

        assert result.code == expected_code
        assert events[:3] == ["clear", "free", "close"]



def test_release_selector_context_frees_tracked_nodes_before_selector(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})
    events = []

    class RecordingRpc(_RpcBase):
        def free_nodes(self, nodes):
            events.append(("free_nodes", int(nodes)))
            return True

        def clear_selector(self, selector):
            events.append(("clear", int(selector)))
            return True

        def free_selector(self, selector):
            events.append(("free_selector", int(selector)))
            return True

        def close(self):
            events.append(("close", None))
            return None

    monkeypatch.setattr(ui_actions, "MytRpc", RecordingRpc)

    assert ui_actions.create_selector({}, ctx).ok is True
    assert ui_actions.selector_find_nodes({"save_as": "nodes_h"}, ctx).ok is True

    released = ui_actions.release_selector_context(ctx)

    assert released is True
    assert "selector" not in ctx.vars
    assert "nodes_h" not in ctx.vars
    assert "_selector_nodes_vars" not in ctx.vars
    assert events == [
        ("free_nodes", 101),
        ("clear", 1),
        ("free_selector", 1),
        ("close", None),
    ]


def test_selector_node_runtime_accessors_work(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpcHasNode)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    assert ui_actions.create_selector({}, ctx).ok is True
    ctx.vars["node_handle"] = 300

    assert ui_actions.node_get_json({}, ctx).ok is True
    assert ui_actions.node_get_text({}, ctx).ok is True
    assert ui_actions.node_get_desc({}, ctx).ok is True
    assert ui_actions.node_get_package({}, ctx).ok is True
    assert ui_actions.node_get_class({}, ctx).ok is True
    assert ui_actions.node_get_id({}, ctx).ok is True
    assert ui_actions.node_get_bound({}, ctx).ok is True
    assert ui_actions.node_get_bound_center({}, ctx).ok is True
    assert ui_actions.node_click({}, ctx).ok is True
    assert ui_actions.node_long_click({}, ctx).ok is True
    assert ui_actions.selector_free({}, ctx).ok is True


def test_ui_actions_rpc_bootstrap_error_contracts(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={})

    monkeypatch.setattr(ui_actions, "_is_rpc_enabled", lambda: False)
    disabled = ui_actions.click({}, ctx)
    assert disabled.ok is False
    assert disabled.code == "rpc_disabled"
    assert disabled.message == "MYT_ENABLE_RPC=0"

    monkeypatch.setattr(ui_actions, "_is_rpc_enabled", lambda: True)
    invalid = ui_actions.click({}, ctx)
    assert invalid.ok is False
    assert invalid.code == "invalid_params"
    assert invalid.message == "device_ip is required"

    class FailingRpc(_RpcBase):
        def init(self, ip, port, timeout) -> bool:
            _ = (ip, port, timeout)
            return False

    monkeypatch.setattr(ui_actions, "MytRpc", FailingRpc)
    failed = ui_actions.click({"device_ip": "192.168.1.2", "rpa_port": 30002}, ctx)
    assert failed.ok is False
    assert failed.code == "rpc_connect_failed"
    assert failed.message == "connect failed: 192.168.1.2:30002"
