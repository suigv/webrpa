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
        return True

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


def test_node_field_and_click_actions(monkeypatch):
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
