from types import SimpleNamespace

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


class FakeRpc:
    def init(self, ip, port, timeout):
        return True

    def close(self):
        return None

    def touchClick(self, finger_id, x, y):
        return True

    def swipe(self, finger_id, x0, y0, x1, y1, duration):
        return True

    def longClick(self, finger_id, x, y, duration):
        return True

    def sendText(self, text):
        return True

    def keyPress(self, code):
        return True

    def openApp(self, package):
        return True

    def stopApp(self, package):
        return True

    def exec_cmd(self, command):
        return ("ok", True)

    def screentshot(self, mode=0, quality=80, save_path=""):
        return save_path or "shot.png"

    def dump_node_xml(self, dump_all):
        return "<xml/>"

    def dump_node_xml_ex(self, work_mode, timeout_ms):
        return "<xml-ex/>"

    def create_selector(self):
        return 123

    def addQuery_Text(self, selector, value):
        return True

    def addQuery_Clickable(self, selector, value):
        return True

    def clear_selector(self, selector):
        return True

    def execQueryOne(self, selector):
        return SimpleNamespace(text="node")

    def execQueryAll(self, selector):
        return [SimpleNamespace(text="n1"), SimpleNamespace(text="n2")]


def test_ui_core_actions_success(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setattr(ui_actions, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2})

    assert ui_actions.click({"x": 100, "y": 200}, ctx).ok is True
    assert ui_actions.swipe({"x0": 1, "y0": 2, "x1": 3, "y1": 4, "duration": 120}, ctx).ok is True
    assert ui_actions.long_click({"x": 1, "y": 2, "duration": 1.2}, ctx).ok is True
    assert ui_actions.input_text({"text": "abc"}, ctx).ok is True
    assert ui_actions.key_press({"key": "home"}, ctx).ok is True
    assert ui_actions.app_open({"package": "com.demo.app"}, ctx).ok is True
    assert ui_actions.app_stop({"package": "com.demo.app"}, ctx).ok is True
    assert ui_actions.exec_command({"command": "ls"}, ctx).ok is True
    assert ui_actions.dumpNodeXml({}, ctx).ok is True
    assert ui_actions.dump_node_xml_ex({}, ctx).ok is True
    assert ui_actions.screenshot({"save_path": "a.png"}, ctx).ok is True
    assert ui_actions.create_selector({}, ctx).ok is True

    selector = ctx.vars["selector"]
    assert selector.addQuery_Text("hello") is True
    assert selector.addQuery_Clickable(True) is True
    assert selector.execQueryOne().ok is True
    assert selector.execQueryAll().ok is True


def test_ui_action_failure_safe_rpc_disabled(monkeypatch):
    ui_actions = _load_ui_actions_module()
    ExecutionContext = _load_execution_context()
    monkeypatch.setenv("MYT_ENABLE_RPC", "0")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2"})
    result = ui_actions.click({"x": 1, "y": 2}, ctx)
    assert result.ok is False
    assert result.code == "rpc_disabled"


def test_rpc_node_helpers():
    ui_actions = _load_ui_actions_module()
    parent = SimpleNamespace(id="parent")
    children = [SimpleNamespace(id="c1"), SimpleNamespace(id="c2")]
    node = ui_actions.RpcNode(SimpleNamespace(text="t", id="i", class_name="c", package="p", desc="d", bound={"left": 0, "top": 0, "right": 10, "bottom": 20}, children=children, get_node_parent=lambda: parent, Click_events=lambda: True, longClick_events=lambda: True, getNodeJson=lambda: "{}"))
    assert node.get_node_text() == "t"
    assert node.get_node_bound_center() == {"x": 5, "y": 10}
    assert node.get_node_parent().id == "parent"
    assert node.get_node_child_count() == 2
    assert node.get_node_child(1).id == "c2"
    assert node.click_events() is True
    assert node.long_click_events() is True
    assert node.get_node_json() == "{}"
