# pyright: reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportPrivateUsage=false
import ctypes
import importlib
from types import SimpleNamespace

from hardware_adapters.mytRpc import MytRpc


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

    def get_sdk_version(self):
        return b"1.2.3"

    def check_connect_state(self):
        return True

    def touchDown(self, finger_id, x, y):
        return True

    def touchUp(self, finger_id, x, y):
        return True

    def touchMove(self, finger_id, x, y):
        return True

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

    def take_capture(self):
        return {"data": b"abcd", "width": 2, "height": 2, "stride": 2}

    def take_capture_ex(self, left, top, right, bottom):
        _ = (left, top, right, bottom)
        return {"data": b"abcd", "width": 2, "height": 2, "stride": 2}

    def take_capture_compress(self, image_type, quality):
        _ = (image_type, quality)
        return b"png"

    def take_capture_compress_ex(self, left, top, right, bottom, image_type, quality):
        _ = (left, top, right, bottom, image_type, quality)
        return b"png"

    def get_display_rotate(self):
        return 1

    def set_rpa_work_mode(self, mode):
        return mode in (0, 1)

    def use_new_node_mode(self, enabled):
        return enabled in (True, False)

    def start_video_stream(self, width, height, bitrate):
        _ = (width, height, bitrate)
        return True

    def stop_video_stream(self):
        return True

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
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 2}
    )

    assert ui_actions.click({"x": 100, "y": 200}, ctx).ok is True
    assert ui_actions.touch_down({"x": 100, "y": 200}, ctx).ok is True
    assert ui_actions.touch_up({"x": 100, "y": 200}, ctx).ok is True
    assert ui_actions.touch_move({"x": 101, "y": 201}, ctx).ok is True
    assert ui_actions.swipe({"x0": 1, "y0": 2, "x1": 3, "y1": 4, "duration": 120}, ctx).ok is True
    assert ui_actions.long_click({"x": 1, "y": 2, "duration": 1.2}, ctx).ok is True
    assert ui_actions.input_text({"text": "abc"}, ctx).ok is True
    assert ui_actions.key_press({"key": "home"}, ctx).ok is True
    assert ui_actions.app_open({"package": "com.demo.app"}, ctx).ok is True
    assert ui_actions.app_stop({"package": "com.demo.app"}, ctx).ok is True
    assert ui_actions.get_sdk_version({}, ctx).ok is True
    assert ui_actions.check_connect_state({}, ctx).ok is True
    assert ui_actions.exec_command({"command": "ls"}, ctx).ok is True
    assert ui_actions.dump_node_xml_ex({}, ctx).ok is True
    assert ui_actions.screenshot({"save_path": "a.png"}, ctx).ok is True
    assert ui_actions.capture_raw({}, ctx).ok is True
    assert ui_actions.capture_compressed({}, ctx).ok is True
    assert ui_actions.get_display_rotate({}, ctx).ok is True
    assert ui_actions.set_work_mode({"mode": 1}, ctx).ok is True
    assert ui_actions.use_new_node_mode({"enabled": True}, ctx).ok is True
    assert (
        ui_actions.start_video_stream({"width": 320, "height": 640, "bitrate": 20000}, ctx).ok
        is True
    )
    assert ui_actions.stop_video_stream({}, ctx).ok is True
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
    node = ui_actions.RpcNode(
        SimpleNamespace(
            text="t",
            id="i",
            class_name="c",
            package="p",
            desc="d",
            bound={"left": 0, "top": 0, "right": 10, "bottom": 20},
            children=children,
            get_node_parent=lambda: parent,
            Click_events=lambda: True,
            longClick_events=lambda: True,
            getNodeJson=lambda: "{}",
        )
    )
    assert node.get_node_text() == "t"
    assert node.get_node_bound_center() == {"x": 5, "y": 10}
    assert node.get_node_parent().id == "parent"
    assert node.get_node_child_count() == 2
    assert node.get_node_child(1).id == "c2"
    assert node.click_events() is True
    assert node.long_click_events() is True
    assert node.get_node_json() == "{}"


def test_myt_rpc_owned_text_calls_free_rpc_ptr(monkeypatch):
    rpc = MytRpc()
    rpc._handle = 1
    allocations: list[ctypes.Array[ctypes.c_char]] = []
    freed: list[int] = []

    def make_ptr(payload: bytes) -> int:
        buf = ctypes.create_string_buffer(payload)
        allocations.append(buf)
        return ctypes.addressof(buf)

    class FakeLib:
        def __init__(self):
            self.execCmd = lambda handle, mode, cmd: make_ptr(b"exec-result")
            self.dumpNodeXml = lambda handle, dump_all: make_ptr(b"<xml/>")
            self.dumpNodeXmlEx = lambda handle, work_mode, timeout_ms: make_ptr(b"<xml-ex/>")
            self.getNodeText = lambda node: make_ptr(b"node-text")
            self.freeRpcPtr = lambda ptr: freed.append(ctypes.cast(ptr, ctypes.c_void_p).value or 0)

    monkeypatch.setattr(rpc, "_rpc", FakeLib())

    assert rpc.exec_cmd("ls") == ("exec-result", True)
    assert rpc.dump_node_xml(True) == "<xml/>"
    assert rpc.dump_node_xml_ex(False, 123) == "<xml-ex/>"
    assert rpc.get_node_text(99) == "node-text"
    assert len(freed) == 4
    assert all(value > 0 for value in freed)


def test_myt_rpc_init_uses_passed_timeout(monkeypatch):
    rpc = MytRpc()
    attempts: list[tuple[bytes, int, int]] = []

    class FakeLib:
        def openDevice(self, ip, port, timeout):
            attempts.append((ip, port, timeout))
            return 1

    monkeypatch.setattr(rpc, "_load_library", lambda: FakeLib())

    assert rpc.init("192.168.1.2", 30002, 37) is True
    assert attempts == [(b"192.168.1.2", 30002, 37)]
