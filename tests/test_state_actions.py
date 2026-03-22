import importlib

from engine.action_registry import register_defaults, resolve_action


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


def test_detect_login_stage_account(monkeypatch):
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

        def addQuery_DescContainWith(self, selector, value):
            _ = (selector, value)
            return True

        def execQueryOne(self, selector):
            _ = selector
            return 1 if self.query_text == "账号" else None

        def free_selector(self, selector):
            _ = selector
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.detect_login_stage(
        {"stage_patterns": {"account": {"text_markers": ["账号"]}}, "stage_order": ["account"]}, ctx
    )
    assert result.ok is True
    assert result.data["stage"] == "account"


def test_ui_match_state_normalizes_native_state_profile_params(monkeypatch):
    register_defaults()
    mod = importlib.import_module("engine.actions.ui_state_actions")
    ExecutionContext = _load_execution_context()

    captured: dict[str, object] = {}

    class FakeAdapter:
        def __init__(self, state_profile_id, *, action_params=None, binding_id=None):
            captured["state_profile_id"] = state_profile_id
            captured["binding_id"] = binding_id
            captured["action_params"] = dict(action_params or {})

        def match_state(self, context, *, expected_state_ids, timeout_ms=None):
            _ = (context, expected_state_ids, timeout_ms)

            class _Result:
                def to_action_result(self):
                    return importlib.import_module("engine.models.runtime").ActionResult(
                        ok=True, code="ok", data={"state": {"state_id": "available"}}
                    )

            return _Result()

    monkeypatch.setattr(mod, "NativeUIStateAdapter", FakeAdapter)

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = resolve_action("ui.match_state")(
        {
            "platform": "native",
            "state_profile_id": "feed_profile",
            "binding_id": "legacy_profile",
            "expected_state_ids": ["available"],
        },
        ctx,
    )

    assert result.ok is True
    assert captured["state_profile_id"] == "feed_profile"
    assert captured["binding_id"] is None
    action_params = captured["action_params"]
    assert isinstance(action_params, dict)
    assert action_params["state_profile_id"] == "feed_profile"
    assert "binding_id" not in action_params


def test_ui_match_state_keeps_binding_id_entrypoint_compatibility(monkeypatch):
    register_defaults()
    mod = importlib.import_module("engine.actions.ui_state_actions")
    ExecutionContext = _load_execution_context()

    captured: dict[str, object] = {}

    class FakeAdapter:
        def __init__(self, state_profile_id, *, action_params=None, binding_id=None):
            captured["state_profile_id"] = state_profile_id
            captured["binding_id"] = binding_id
            captured["action_params"] = dict(action_params or {})

        def match_state(self, context, *, expected_state_ids, timeout_ms=None):
            _ = (context, expected_state_ids, timeout_ms)

            class _Result:
                def to_action_result(self):
                    return importlib.import_module("engine.models.runtime").ActionResult(
                        ok=True, code="ok", data={"state": {"state_id": "available"}}
                    )

            return _Result()

    monkeypatch.setattr(mod, "NativeUIStateAdapter", FakeAdapter)

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = resolve_action("ui.match_state")(
        {
            "platform": "native",
            "binding_id": "legacy_profile",
            "expected_state_ids": ["available"],
        },
        ctx,
    )

    assert result.ok is True
    assert captured["state_profile_id"] == "legacy_profile"
    assert captured["binding_id"] is None
    action_params = captured["action_params"]
    assert isinstance(action_params, dict)
    assert action_params["state_profile_id"] == "legacy_profile"
    assert "binding_id" not in action_params


def test_detect_login_stage_uses_visible_japanese_login_entry_text(monkeypatch):
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" password="false" bounds="[0,0][720,1280]">
                <node text="Googleのアカウントで続ける" resource-id="com.twitter.android:id/ocf_button" class="android.widget.Button" package="com.twitter.android" password="false" bounds="[80,743][640,827]"/>
                <node text="アカウントを作成" resource-id="com.twitter.android:id/cta" class="android.widget.Button" package="com.twitter.android" password="false" bounds="[80,860][640,944]"/>
                <node text="ログイン" resource-id="com.twitter.android:id/login" class="android.widget.TextView" package="com.twitter.android" password="false" bounds="[312,1010][408,1060]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def exec_cmd(self, command):
            _ = command
            return "", True

        def create_selector(self):
            raise AssertionError("selector RPC should not be used when XML detection succeeds")

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.detect_login_stage(
        {
            "stage_patterns": {
                "password": {"text_markers": ["password"]},
                "login_entry": {"text_markers": ["ログイン", "アカウントを作成"]},
            },
            "stage_order": ["password", "login_entry"],
        },
        ctx,
    )

    assert result.ok is True
    assert result.data["stage"] == "login_entry"


def test_detect_login_stage_uses_attribute_fallback_for_truncated_xml(monkeypatch):
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
            return (
                '<?xml version="1.0"?><hierarchy><node text="" resource-id="" class="android.widget.FrameLayout" '
                'package="com.twitter.android" password="false"><node text="始めるには、まず電話番号、メールアドレス、またはユーザー名を入力してください" '
                'resource-id="com.twitter.android:id/primary_text" class="android.widget.TextView" package="com.twitter.android" password="false" />'
                '<node text="" resource-id="com.twitter.android:id/identifier" class="android.widget.EditText" package="com.twitter.android" '
                'content-desc="電話番号/メールアドレス/ユーザー名" password="false"'
            )

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def exec_cmd(self, command):
            _ = command
            return "", True

        def create_selector(self):
            raise AssertionError("selector RPC should not be used when attribute fallback succeeds")

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.detect_login_stage(
        {
            "stage_patterns": {
                "account": {"text_markers": ["電話番号", "メールアドレス", "ユーザー名"]},
            },
            "stage_order": ["account"],
        },
        ctx,
    )

    assert result.ok is True
    assert result.data["stage"] == "account"


def test_detect_login_stage_prefers_account_over_forgot_password_link(monkeypatch):
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android">
                <node text="始めるには、まず電話番号、メールアドレス、またはユーザー名を入力してください" resource-id="com.twitter.android:id/primary_text" class="android.widget.TextView" package="com.twitter.android"/>
                <node text="電話番号/メールアドレス/ユーザー名" resource-id="com.twitter.android:id/identifier" class="android.widget.EditText" package="com.twitter.android"/>
                <node text="パスワードを忘れた場合はこちら" resource-id="com.twitter.android:id/secondary_button" class="android.widget.Button" package="com.twitter.android"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def exec_cmd(self, command):
            _ = command
            return "", True

        def create_selector(self):
            raise AssertionError("selector RPC should not be used when XML detection succeeds")

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.detect_login_stage({}, ctx)

    # Architecture 2.0: no global text_markers — without explicit patterns,
    # the system must return 'unknown' and defer to AI visual inference.
    assert result.ok is True
    assert result.data["stage"] == "unknown"


def test_wait_login_stage_until_home(monkeypatch):
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

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.wait_login_stage(
        {
            "target_stages": ["home"],
            "timeout_ms": 3000,
            "interval_ms": 10,
            "stage_patterns": {"home": {"focus_markers": ["home"]}},
            "stage_order": ["home"],
        },
        ctx,
    )
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="ignored top" resource-id="com.example.app:id/row" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,10][1080,180]"/>
                <node text="" resource-id="com.example.app:id/row" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,420][1080,980]">
                  <node text="PayPay 配布 5000円" resource-id="" class="android.widget.TextView" package="com.example.app" bounds="[50,450][900,520]"/>
                  <node text="" content-desc="promo card" resource-id="" class="android.widget.ImageView" package="com.example.app" bounds="[50,540][900,920]"/>
                </node>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.extract_search_candidates({"package": "com.example.app"}, ctx)
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
                  <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                    <node text="" resource-id="com.example.app:id/row" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,420][1080,980]">
                      <node text="Demo User @demo_handle PayPay 配布" class="android.widget.TextView" package="com.example.app" bounds="[50,450][900,520]"/>
                    </node>
                  </node>
                </hierarchy>
                """,
                """
                <hierarchy>
                  <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                    <node text="" resource-id="com.example.app:id/row" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,420][1080,980]">
                      <node text="Next User @next_handle 現金配布" class="android.widget.TextView" package="com.example.app" bounds="[50,450][900,520]"/>
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
    result = mod.collect_blogger_candidates(
        {"package": "com.example.app", "max_rounds": 2, "max_candidates": 5}, ctx
    )
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="" content-desc="Alice：你好，最近怎么样。12:20" class="android.view.View" package="com.example.app" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：稍后回复。12:21" class="android.view.View" package="com.example.app" bounds="[620,800][1020,900]"/>
                <node text="" content-desc="Bob：最后一条消息。12:25" class="android.view.View" package="com.example.app" bounds="[40,980][520,1100]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.extract_dm_last_message({"package": "com.example.app"}, ctx)
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="" content-desc="Alice：你好，最近怎么样。12:20" class="android.view.View" package="com.example.app" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：我刚发出的回复。12:31" class="android.view.View" package="com.example.app" bounds="[620,980][1020,1100]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = mod.extract_dm_last_outbound_message({"package": "com.example.app"}, ctx)
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="Follow" class="android.widget.Button" package="com.example.app" bounds="[780,500][980,580]"/>
                <node text="フォローする" class="android.widget.Button" package="com.example.app" bounds="[780,720][980,800]"/>
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

    extracted = mod.extract_follow_targets({"package": "com.example.app"}, ctx)
    assert extracted.ok is True
    assert extracted.data["count"] == 2

    followed = mod.follow_visible_targets({"package": "com.example.app", "max_clicks": 2}, ctx)
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="未読 2" content-desc="Unread conversation" class="android.view.View" package="com.example.app" bounds="[30,500][980,680]"/>
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

    extracted = mod.extract_unread_dm_targets({"package": "com.example.app"}, ctx)
    assert extracted.ok is True
    assert extracted.data["count"] == 1

    opened = mod.open_first_unread_dm({"package": "com.example.app"}, ctx)
    assert opened.ok is True
    assert opened.data["count"] == 1


def test_state_actions_rpc_bootstrap_error_contracts(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={})

    monkeypatch.setattr(mod, "_is_rpc_enabled", lambda: False)
    disabled = mod.detect_login_stage({}, ctx)
    assert disabled.ok is False
    assert disabled.code == "rpc_disabled"
    assert disabled.message == "MYT_ENABLE_RPC=0"

    monkeypatch.setattr(mod, "_is_rpc_enabled", lambda: True)
    invalid = mod.detect_login_stage({}, ctx)
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
    failed = mod.detect_login_stage({"device_ip": "192.168.1.214", "rpa_port": 30002}, ctx)
    assert failed.ok is False
    assert failed.code == "rpc_connect_failed"
    assert failed.message == "connect failed: 192.168.1.214:30002"


def test_ui_state_action_wrappers_preserve_legacy_native_contracts(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()
    register_defaults()

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

        def addQuery_DescContainWith(self, selector, value):
            _ = (selector, value)
            return True

        def execQueryOne(self, selector):
            _ = selector
            return 1 if self.query_text == "账号" else None

        def free_selector(self, selector):
            _ = selector
            return True

    monkeypatch.setattr(mod, "MytRpc", FakeRpc)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )

    service_result = resolve_action("ui.match_state")(
        {
            "platform": "native",
            "state_profile_id": "login_stage",
            "expected_state_ids": ["account", "home"],
            "stage_patterns": {"account": {"text_markers": ["账号"]}},
            "stage_order": ["account"],
        },
        ctx,
    )
    legacy_result = resolve_action("core.detect_login_stage")(
        {"stage_patterns": {"account": {"text_markers": ["账号"]}}, "stage_order": ["account"]},
        ctx,
    )

    assert service_result.ok is True
    assert service_result.code == "ok"
    assert service_result.data["operation"] == "match_state"
    assert service_result.data["platform"] == "native"
    assert service_result.data["state"]["state_id"] == "account"
    assert service_result.data["raw_details"]["stage"] == "account"
    assert legacy_result.ok is True
    assert legacy_result.data == {"stage": "account"}


def test_detect_app_stage_prefers_stage_patterns_from_app_config(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    captured: dict[str, object] = {}

    monkeypatch.setattr(mod, "_connect_rpc", lambda params, context: (object(), None))
    monkeypatch.setattr(mod, "_close_rpc", lambda rpc: None)

    def _fake_detect(rpc, params, context):
        _ = (rpc, context)
        captured["params"] = params
        return "home"

    monkeypatch.setattr(mod, "_detect_login_stage_with_rpc", _fake_detect)
    monkeypatch.setattr(mod.sdk_config_support, "app_from_package", lambda package: "x")
    monkeypatch.setattr(
        mod.sdk_config_support,
        "load_app_config_document",
        lambda app: {
            "stage_patterns": {
                "home": {
                    "resource_ids": ["com.twitter.android:id/home_timeline"],
                    "text_markers": ["For you"],
                }
            },
            "selectors": {"follow_button": {"type": "text", "mode": "equal", "value": "Follow"}},
        },
    )

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.detect_app_stage({"package": "com.twitter.android"}, ctx)

    assert result.ok is True
    assert result.data == {"stage": "home"}
    assert captured["params"] == {
        "stage_patterns": {
            "home": {
                "resource_ids": ["com.twitter.android:id/home_timeline"],
                "focus_markers": [],
                "text_markers": ["For you"],
            }
        },
        "stage_order": ["home"],
    }


def test_detect_app_stage_falls_back_to_legacy_stage_like_selectors(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    captured: dict[str, object] = {}

    monkeypatch.setattr(mod, "_connect_rpc", lambda params, context: (object(), None))
    monkeypatch.setattr(mod, "_close_rpc", lambda rpc: None)

    def _fake_detect(rpc, params, context):
        _ = (rpc, context)
        captured["params"] = params
        return "home"

    monkeypatch.setattr(mod, "_detect_login_stage_with_rpc", _fake_detect)
    monkeypatch.setattr(mod.sdk_config_support, "app_from_package", lambda package: "x")
    monkeypatch.setattr(
        mod.sdk_config_support,
        "load_app_config_document",
        lambda app: {
            "selectors": {
                "home": {
                    "resource_ids": ["com.twitter.android:id/home_timeline"],
                    "content_descs": ["Timeline"],
                },
                "follow_button": {"type": "text", "mode": "equal", "value": "Follow"},
            }
        },
    )

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = mod.detect_app_stage({"package": "com.twitter.android"}, ctx)

    assert result.ok is True
    assert result.data == {"stage": "home"}
    assert captured["params"] == {
        "stage_patterns": {
            "home": {
                "resource_ids": ["com.twitter.android:id/home_timeline"],
                "focus_markers": [],
                "text_markers": ["Timeline"],
            }
        },
        "stage_order": ["home"],
    }


def test_detect_app_stage_uses_injected_stage_patterns_when_params_absent(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    captured: dict[str, object] = {}

    monkeypatch.setattr(mod, "_connect_rpc", lambda params, context: (object(), None))
    monkeypatch.setattr(mod, "_close_rpc", lambda rpc: None)

    def _fake_detect(rpc, params, context):
        _ = (rpc, context)
        captured["params"] = params
        return "home"

    monkeypatch.setattr(mod, "_detect_login_stage_with_rpc", _fake_detect)
    monkeypatch.setattr(
        mod.sdk_config_support,
        "load_app_config_document",
        lambda app: (_ for _ in ()).throw(AssertionError("config fallback should not run")),
    )

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214"},
        session={
            "defaults": {
                "package": "com.twitter.android",
                "_app_stage_patterns": {"home": {"text_markers": ["For you"]}},
            }
        },
    )
    result = mod.detect_app_stage({}, ctx)

    assert result.ok is True
    assert result.data == {"stage": "home"}
    assert captured["params"] == {
        "stage_patterns": {
            "home": {"resource_ids": [], "focus_markers": [], "text_markers": ["For you"]}
        },
        "stage_order": ["home"],
    }


def test_detect_app_stage_explicit_stage_patterns_override_injected_defaults(monkeypatch):
    mod = _load_state_actions_module()
    ExecutionContext = _load_execution_context()

    captured: dict[str, object] = {}

    monkeypatch.setattr(mod, "_connect_rpc", lambda params, context: (object(), None))
    monkeypatch.setattr(mod, "_close_rpc", lambda rpc: None)

    def _fake_detect(rpc, params, context):
        _ = (rpc, context)
        captured["params"] = params
        return "search"

    monkeypatch.setattr(mod, "_detect_login_stage_with_rpc", _fake_detect)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214"},
        session={
            "defaults": {
                "package": "com.twitter.android",
                "_app_stage_patterns": {"home": {"text_markers": ["For you"]}},
            }
        },
    )
    result = mod.detect_app_stage(
        {"stage_patterns": {"search": {"text_markers": ["Search"]}}},
        ctx,
    )

    assert result.ok is True
    assert result.data == {"stage": "search"}
    assert captured["params"] == {
        "stage_patterns": {
            "search": {"resource_ids": [], "focus_markers": [], "text_markers": ["Search"]}
        },
        "stage_order": ["search"],
    }


def test_ui_state_action_wrappers_expose_browser_contract_and_aliases():
    ExecutionContext = _load_execution_context()
    register_defaults()

    class FakeBrowser:
        def __init__(self, *, existing=None, url="", wait_result=False):
            self.available = True
            self.error = ""
            self.error_code = ""
            self._existing = existing or set()
            self._url = url
            self._wait_result = wait_result
            self.wait_calls = []

        def exists(self, selector):
            return selector in self._existing

        def html(self):
            return "<body>Login</body>"

        def current_url(self):
            return self._url

        def wait_url_contains(self, fragment, timeout_seconds):
            self.wait_calls.append((fragment, timeout_seconds))
            return self._wait_result

    browser_ctx = ExecutionContext(payload={})
    browser_ctx.browser = FakeBrowser(existing={"#login"}, url="https://example.com/login")
    browser_match = resolve_action("browser.match_state")(
        {"expected_state_ids": ["exists:#login"]}, browser_ctx
    )

    wait_ctx = ExecutionContext(payload={})
    wait_ctx.browser = FakeBrowser(url="https://example.com/home", wait_result=True)
    browser_wait = resolve_action("browser.wait_until")(
        {"expected_state_ids": ["url:/home"], "timeout_ms": 2000}, wait_ctx
    )

    transition_ctx = ExecutionContext(payload={})
    transition_ctx.browser = FakeBrowser(
        existing={"#login"}, url="https://example.com/home", wait_result=True
    )
    transition = resolve_action("ui.observe_transition")(
        {
            "platform": "browser",
            "from_state_ids": ["exists:#login"],
            "to_state_ids": ["url:/home"],
            "timeout_ms": 2000,
            "interval_ms": 100,
        },
        transition_ctx,
    )

    assert browser_match.ok is True
    assert browser_match.data["state"]["state_id"] == "exists:#login"
    assert browser_match.data["platform"] == "browser"
    assert browser_wait.ok is True
    assert browser_wait.data["operation"] == "wait_until"
    assert wait_ctx.browser.wait_calls == [("/home", 2)]
    assert transition.ok is True
    assert transition.data["operation"] == "observe_transition"
    assert transition.data["status"] == "transition_observed"
    assert transition.data["transition"]["from_state"]["state_id"] == "exists:#login"
    assert transition.data["transition"]["to_state"]["state_id"] == "url:/home"
