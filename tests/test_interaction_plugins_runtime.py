# pyright: reportMissingModuleSource=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnusedImport=false

from typing import Optional, cast

from engine.runner import Runner


def test_dm_reply_script_uses_ui_state_service_for_observation_steps():
    from pathlib import Path
    import yaml

    script_path = Path(__file__).resolve().parents[1] / "plugins" / "dm_reply" / "script.yaml"
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))
    steps = cast(list[dict[str, object]], script["steps"])
    labels = cast(dict[str, dict[str, object]], {step["label"]: step for step in steps if step.get("label")})
    observe_unread_params = cast(dict[str, object], labels["observe_unread_dm_target"]["params"])
    check_unread_when = cast(dict[str, object], labels["check_unread_dm_available"]["when"])
    check_unread_all = cast(list[dict[str, object]], check_unread_when["all"])
    observe_last_params = cast(dict[str, object], labels["observe_last_dm_message"]["params"])
    check_last_when = cast(dict[str, object], labels["check_last_dm_message_available"]["when"])
    check_last_all = cast(list[dict[str, object]], check_last_when["all"])
    observe_sent_params = cast(dict[str, object], labels["observe_last_sent_dm_message"]["params"])
    check_sent_when = cast(dict[str, object], labels["check_last_sent_dm_message_available"]["when"])
    check_sent_all = cast(list[dict[str, object]], check_sent_when["all"])

    assert labels["observe_unread_dm_target"]["action"] == "ui.match_state"
    assert observe_unread_params["binding_id"] == "dm_unread"
    assert check_unread_all[0]["var"] == "unread_dm_observation.state.state_id"
    assert labels["open_first_unread_dm"]["action"] == "core.open_candidate"
    assert labels["observe_last_dm_message"]["action"] == "ui.match_state"
    assert observe_last_params["binding_id"] == "dm_last_message"
    assert check_last_all[0]["var"] == "last_dm_message.state.state_id"
    assert labels["observe_last_sent_dm_message"]["action"] == "ui.match_state"
    assert observe_sent_params["binding_id"] == "dm_last_outbound_message"
    assert check_sent_all[0]["var"] == "last_sent_dm_message.state.state_id"


def test_follow_plugin_success_and_home_requires_live_rpc(monkeypatch):
    monkeypatch.setenv("MYT_ENABLE_RPC", "0")
    follow = Runner().run({"task": "follow_interaction", "device_ip": "192.168.1.2", "target_username": "demo", "status_hint": "success"})
    home = Runner().run({"task": "home_interaction", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert follow["status"] == "success"
    assert home["status"] == "failed"
    assert "rpc_disabled" in home.get("message", "")


def test_follow_plugin_follows_visible_targets_when_rpc_available(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

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
                <node text="Follow" class="android.widget.Button" package="com.twitter.android" bounds="[780,500][980,580]"/>
                <node text="Follow" class="android.widget.Button" package="com.twitter.android" bounds="[780,720][980,800]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = (finger_id, x, y)
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr("engine.actions.state_actions.time.sleep", lambda *_: None)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))

    result = Runner().run({"task": "follow_interaction", "device_ip": "192.168.1.2", "target_username": "demo"})
    assert result["status"] == "success"

    payload = (tmp_path / "config" / "data" / "migration_shared.json").read_text(encoding="utf-8")
    assert "follow_last_result" in payload


def test_interaction_plugins_rate_limit_and_empty_target():
    follow_limit = Runner().run({"task": "follow_interaction", "device_ip": "192.168.1.2", "target_username": "demo", "status_hint": "rate_limit"})
    home_empty = Runner().run({"task": "home_interaction", "device_ip": "192.168.1.2", "status_hint": "empty_target"})
    assert follow_limit["status"] == "failed"
    assert "rate_limit" in follow_limit.get("message", "")
    assert home_empty["status"] == "failed"
    assert "empty_target" in home_empty.get("message", "")


def test_quote_and_dm_plugin_templates_available():
    quote = Runner().run({"task": "quote_interaction", "device_ip": "192.168.1.2", "status_hint": "success"})
    dm = Runner().run({"task": "dm_reply", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert quote["status"] == "success"
    assert dm["status"] == "success"


def test_quote_and_dm_plugins_execute_minimal_runtime_flow(monkeypatch, tmp_path):
    from engine.actions import sdk_actions, state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    class FakeClient:
        device_ip: str

        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip

        def auto_click(self, enabled: Optional[bool] = None, interval_ms: Optional[int] = None, **kwargs):
            _ = (enabled, interval_ms)
            return {"ok": True, "data": kwargs}

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
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
                <node text="" content-desc="Alice：hello dm。12:20" class="android.view.View" package="com.twitter.android" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：hello dm。12:21" class="android.view.View" package="com.twitter.android" bounds="[620,760][1020,860]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(sdk_actions, "MytSdkClient", FakeClient)
    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    quote = Runner().run(
        {
            "task": "quote_interaction",
            "device_ip": "192.168.1.2",
            "target_post_url": "https://x.com/demo/status/1",
            "quote_text": "hello quote",
        }
    )
    dm = Runner().run(
        {
            "task": "dm_reply",
            "device_ip": "192.168.1.2",
            "reply_text": "hello dm",
        }
    )

    assert quote["status"] == "success"
    assert dm["status"] == "success"


def test_quote_and_dm_plugins_generate_text_when_missing(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

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
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
                <node text="" content-desc="Alice：hello dm。12:20" class="android.view.View" package="com.twitter.android" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：收到，我先看一下细节。12:21" class="android.view.View" package="com.twitter.android" bounds="[620,760][1020,860]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = (finger_id, x, y)
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    quote = Runner().run(
        {
            "task": "quote_interaction",
            "device_ip": "192.168.1.2",
            "target_post_url": "https://x.com/demo/status/1",
            "source_text": "这是一个待引用的帖子",
        }
    )
    dm = Runner().run(
        {
            "task": "dm_reply",
            "device_ip": "192.168.1.2",
            "ai_type": "part_time",
        }
    )

    assert quote["status"] == "success"
    assert dm["status"] == "success"


def test_quote_plugin_can_search_target_username_when_post_url_missing(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

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
                <node text="" resource-id="com.twitter.android:id/row" class="android.widget.LinearLayout" package="com.twitter.android" bounds="[0,420][1080,980]">
                  <node text="Demo User @demo_handle 这是回复内容" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
                </node>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = (finger_id, x, y)
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    quote = Runner().run(
        {
            "task": "quote_interaction",
            "device_ip": "192.168.1.2",
            "target_username": "demo_handle",
        }
    )

    assert quote["status"] == "success"


def test_quote_plugin_skips_already_processed_target(monkeypatch, tmp_path):
    from engine.actions import ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    first = Runner().run(
        {
            "task": "quote_interaction",
            "device_ip": "192.168.1.2",
            "target_post_url": "https://x.com/demo/status/1",
            "quote_text": "hello quote",
        }
    )
    second = Runner().run(
        {
            "task": "quote_interaction",
            "device_ip": "192.168.1.2",
            "target_post_url": "https://x.com/demo/status/1",
            "quote_text": "hello quote",
        }
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert "already_processed" in second.get("message", "")


def test_dm_plugin_extracts_last_message_before_reply(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

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
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
                <node text="" content-desc="Alice：最后一条私信。12:20" class="android.view.View" package="com.twitter.android" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：hello dm。12:21" class="android.view.View" package="com.twitter.android" bounds="[620,760][1020,860]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    result = Runner().run({"task": "dm_reply", "device_ip": "192.168.1.2", "reply_text": "hello dm"})
    assert result["status"] == "success"

    payload = (tmp_path / "config" / "data" / "migration_shared.json").read_text(encoding="utf-8")
    assert "dm_last_sent_message" in payload


def test_dm_plugin_opens_first_unread_from_service_target_payload(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    class FakeRpc:
        clicks: list[tuple[int, int]] = []

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
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
                <node text="" content-desc="Alice：最后一条私信。12:20" class="android.view.View" package="com.twitter.android" bounds="[30,600][500,720]"/>
                <node text="" content-desc="Me：hello dm。12:21" class="android.view.View" package="com.twitter.android" bounds="[620,760][1020,860]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = finger_id
            type(self).clicks.append((x, y))
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    result = Runner().run({"task": "dm_reply", "device_ip": "192.168.1.2", "reply_text": "hello dm"})

    assert result["status"] == "success"
    assert FakeRpc.clicks == [(505, 590)]


def test_dm_plugin_skip_message_save_when_observation_missing(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

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
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = (finger_id, x, y)
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    result = Runner().run({"task": "dm_reply", "device_ip": "192.168.1.2", "reply_text": "hello dm"})
    assert result["status"] == "success"

    store_path = tmp_path / "config" / "data" / "migration_shared.json"
    if store_path.exists():
        payload = store_path.read_text(encoding="utf-8")
        assert "dm_last_message" not in payload
        assert "dm_last_sent_message" not in payload


def test_home_plugin_extracts_candidate_when_rpc_available(monkeypatch, tmp_path):
    from engine.actions import sdk_actions, state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    class FakeClient:
        device_ip: str

        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip

        def auto_click(self, enabled: Optional[bool] = None, interval_ms: Optional[int] = None, **kwargs):
            _ = (enabled, interval_ms)
            return {"ok": True, "data": kwargs}

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
                <node text="" resource-id="com.twitter.android:id/row" class="android.widget.LinearLayout" package="com.twitter.android" bounds="[0,420][1080,980]">
                  <node text="PayPay 配布 5000円" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
                </node>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all):
            _ = dump_all
            return ""

        def touchClick(self, finger_id, x, y):
            _ = (finger_id, x, y)
            return True

    monkeypatch.setattr(sdk_actions, "MytSdkClient", FakeClient)
    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "app_open", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))

    result = Runner().run({"task": "home_interaction", "device_ip": "192.168.1.2", "ai_type": "part_time"})
    assert result["status"] == "success"

    payload = (tmp_path / "config" / "data" / "migration_shared.json").read_text(encoding="utf-8")
    assert "home_last_interaction" in payload
