from engine.runner import Runner


def test_nurture_plugin_success_status_contract():
    result = Runner().run({"task": "nurture", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert result["task"] == "nurture"
    assert result["status"] == "success"


def test_nurture_plugin_enforces_daily_limit(monkeypatch, tmp_path):
    from engine.action_registry import register_defaults, resolve_action
    from engine.models.runtime import ExecutionContext

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))
    register_defaults()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.2"})

    increment = resolve_action("core.increment_daily_counter")
    check = resolve_action("core.check_daily_limit")

    for _ in range(5):
        result = increment({"key": "nurture_daily_count_volc", "scope": "device", "amount": 1}, ctx)
        assert result.ok is True

    blocked = check({"key": "nurture_daily_count_volc", "scope": "device", "limit": 5}, ctx)
    assert blocked.ok is False
    assert blocked.code == "daily_limit_reached"


def test_nurture_plugin_executes_minimal_runtime_flow(monkeypatch, tmp_path):
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
                  <node text="#裏垢女子 filter:images min_faves:50" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
                  <node text="" content-desc="photo" class="android.widget.ImageView" package="com.twitter.android" bounds="[50,540][900,920]"/>
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

    result = Runner().run({"task": "nurture", "device_ip": "192.168.1.2", "ai_type": "volc"})
    assert result["task"] == "nurture"
    assert result["status"] == "success"

    payload = (tmp_path / "config" / "data" / "migration_shared.json").read_text(encoding="utf-8")
    assert "nurture_last_interaction" in payload
