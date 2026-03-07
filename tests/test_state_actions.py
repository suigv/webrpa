import importlib


def _load_state_actions_module():
    for name in ("engine.actions.state_actions", "engine.actions.state_actions"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import state_actions module")


def _load_execution_context():
    for name in ("engine.models.runtime", "engine.models.runtime"):
        try:
            return importlib.import_module(name).ExecutionContext
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import ExecutionContext")


def test_detect_x_login_stage_account(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def __init__(self):
            self.query_text = ""

        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def exec_cmd(self, command):
            _ = command
            return "", True

        def create_selector(self):
            return 1

        def clear_selector(self, selector):
            _ = selector
            return True

        def addQuery_TextContainWith(self, selector, value):
            _ = selector
            self.query_text = value
            return True

        def execQueryOne(self, selector):
            _ = selector
            return 1 if self.query_text == "已有账号" else None

        def free_selector(self, selector):
            _ = selector
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}})
    result = mod.detect_x_login_stage({}, ctx)
    assert result.ok is True
    assert result.data["stage"] == "account"


def test_wait_x_login_stage_until_home(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        calls = 0

        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def exec_cmd(self, command):
            _ = command
            type(self).calls += 1
            if type(self).calls >= 2:
                return "mCurrentFocus=...home...", True
            return "mCurrentFocus=...login...", True

        def create_selector(self):
            return 1

        def clear_selector(self, selector):
            _ = selector
            return True

        def addQuery_TextContainWith(self, selector, value):
            _ = (selector, value)
            return True

        def execQueryOne(self, selector):
            _ = selector
            return None

        def free_selector(self, selector):
            _ = selector
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}})
    result = mod.wait_x_login_stage({"target_stages": ["home"], "timeout_ms": 3000, "interval_ms": 10}, ctx)
    assert result.ok is True
    assert result.data["stage"] == "home"


def test_extract_search_candidates_from_xml(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                <node text="ignored top" resource-id="com.twitter.android:id/row" class="android.widget.LinearLayout" package="com.twitter.android" bounds="[0,10][1080,180]"/>
                <node text="" resource-id="com.twitter.android:id/row" class="android.widget.LinearLayout" package="com.twitter.android" bounds="[0,420][1080,980]">
                  <node text="PayPay 配布 5000円" resource-id="" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
                  <node text="" content-desc="promo card" resource-id="" class="android.widget.ImageView" package="com.twitter.android" bounds="[50,540][900,920]"/>
                </node>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.extract_search_candidates({"package": "com.twitter.android"}, ctx)
    assert result.ok is True
    assert result.data["count"] == 1
    candidate = result.data["candidates"][0]
    assert "PayPay" in candidate["text"]
    assert candidate["has_media"] is True


def test_collect_blogger_candidates_across_rounds(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def __init__(self):
            self.page = 0
            self.swipes = []

        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            pages = [
                """
                <hierarchy>
                  <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                    <node text="" resource-id="com.twitter.android:id/row" class="android.widget.LinearLayout" package="com.twitter.android" bounds="[0,420][1080,980]">
                      <node text="Demo User @demo_handle PayPay 配布" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
                    </node>
                  </node>
                </hierarchy>
                """,
                """
                <hierarchy>
                  <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                    <node text="" resource-id="com.twitter.android:id/row" class="android.widget.LinearLayout" package="com.twitter.android" bounds="[0,420][1080,980]">
                      <node text="Next User @next_handle 現金配布" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
                    </node>
                  </node>
                </hierarchy>
                """,
            ]
            return pages[min(self.page, len(pages) - 1)]

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def swipe(self, finger_id, x0, y0, x1, y1, duration):
            self.swipes.append((finger_id, x0, y0, x1, y1, duration))
            self.page += 1
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.collect_blogger_candidates({"package": "com.twitter.android", "max_rounds": 2, "max_candidates": 5}, ctx)
    assert result.ok is True
    assert result.data["count"] == 2
    assert result.data["swipe_count"] == 1
    identities = [candidate["identity"] for candidate in result.data["candidates"]]
    assert "user:demo_handle" in identities
    assert "user:next_handle" in identities


def test_open_candidate_clicks_candidate_center(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def __init__(self):
            self.clicked = []

        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def touchClick(self, finger_id, x, y):
            self.clicked.append((finger_id, x, y))
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.open_candidate(
        {"candidate": {"bound": {"left": 10, "top": 100, "right": 210, "bottom": 300}}},
        ctx,
    )
    assert result.ok is True
    assert result.data["x"] == 110
    assert result.data["y"] == 200


def test_extract_dm_last_message_from_xml(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                <node text="" content-desc="Alice：你好，最近怎么样。12:20" class="android.view.View" package="com.twitter.android" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：稍后回复。12:21" class="android.view.View" package="com.twitter.android" bounds="[620,800][1020,900]"/>
                <node text="" content-desc="Bob：最后一条消息。12:25" class="android.view.View" package="com.twitter.android" bounds="[40,980][520,1100]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.extract_dm_last_message({"package": "com.twitter.android"}, ctx)
    assert result.ok is True
    assert result.data["message"] == "最后一条消息。12:25"
    assert "Bob：" in result.data["raw"]


def test_extract_dm_last_outbound_message_from_xml(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                <node text="" content-desc="Alice：你好，最近怎么样。12:20" class="android.view.View" package="com.twitter.android" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：我刚发出的回复。12:31" class="android.view.View" package="com.twitter.android" bounds="[620,980][1020,1100]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.extract_dm_last_outbound_message({"package": "com.twitter.android"}, ctx)
    assert result.ok is True
    assert result.data["message"] == "我刚发出的回复。12:31"


def test_extract_and_follow_visible_targets(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def __init__(self):
            self.clicked = []

        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                <node text="Follow" class="android.widget.Button" package="com.twitter.android" bounds="[780,500][980,580]"/>
                <node text="フォローする" class="android.widget.Button" package="com.twitter.android" bounds="[780,720][980,800]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            self.clicked.append((finger_id, x, y))
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})

    extracted = mod.extract_follow_targets({"package": "com.twitter.android"}, ctx)
    assert extracted.ok is True
    assert extracted.data["count"] == 2

    followed = mod.follow_visible_targets({"package": "com.twitter.android", "max_clicks": 2}, ctx)
    assert followed.ok is True
    assert followed.data["clicked_count"] == 2


def test_extract_and_open_first_unread_dm(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    class FakeRpc:
        def __init__(self):
            self.clicked = []

        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return True

        def close(self):
            return None

        def dump_node_xml_ex(self, work_mode, timeout_ms):
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                <node text="未読 2" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            self.clicked.append((finger_id, x, y))
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})

    extracted = mod.extract_unread_dm_targets({"package": "com.twitter.android"}, ctx)
    assert extracted.ok is True
    assert extracted.data["count"] == 1

    opened = mod.open_first_unread_dm({"package": "com.twitter.android"}, ctx)
    assert opened.ok is True
    assert opened.data["count"] == 1


def test_state_actions_rpc_bootstrap_error_contracts(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={})

    monkeypatch.setattr(mod, "_is_rpc_enabled", lambda: False)
    disabled = mod.detect_x_login_stage({}, ctx)
    assert disabled.ok is False
    assert disabled.code == "rpc_disabled"
    assert disabled.message == "MYT_ENABLE_RPC=0"

    monkeypatch.setattr(mod, "_is_rpc_enabled", lambda: True)
    invalid = mod.detect_x_login_stage({}, ctx)
    assert invalid.ok is False
    assert invalid.code == "invalid_params"
    assert invalid.message == "device_ip is required"

    class FailingRpc:
        def init(self, ip, port, timeout):
            _ = (ip, port, timeout)
            return False

        def close(self):
            return None

    monkeypatch.setattr(mod, "MytRpc", FailingRpc)
    failed = mod.detect_x_login_stage({"device_ip": "192.168.1.214", "rpa_port": 30002}, ctx)
    assert failed.ok is False
    assert failed.code == "rpc_connect_failed"
    assert failed.message == "connect failed: 192.168.1.214:30002"
