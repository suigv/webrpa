from engine.runner import Runner


def test_scrape_clone_chain_success(monkeypatch):
    from engine.actions import ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_ENABLE_RPC", "0")
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    scrape = Runner().run(
        {
            "task": "blogger_scrape",
            "device_ip": "192.168.1.2",
            "source_key": "k1",
            "username": "u1",
            "display_name": "U1",
        }
    )
    clone = Runner().run({"task": "profile_clone", "device_ip": "192.168.1.2", "source_key": "k1"})
    assert scrape["status"] == "success"
    assert clone["status"] == "success"


def test_profile_clone_missing_source_data():
    clone = Runner().run({"task": "profile_clone", "source_key": "missing_k"})
    assert clone["status"] == "failed"
    assert "missing_source_data" in clone.get("message", "")


def test_profile_clone_requires_device_ip_when_source_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))
    monkeypatch.setenv("MYT_ENABLE_RPC", "0")
    scrape = Runner().run({"task": "blogger_scrape", "source_key": "k1", "username": "u1", "display_name": "U1"})
    clone = Runner().run({"task": "profile_clone", "source_key": "k1"})
    assert scrape["status"] == "success"
    assert clone["status"] == "failed"
    assert "missing_device_ip" in clone.get("message", "")


def test_blogger_scrape_persists_pool_and_counter(monkeypatch, tmp_path):
    from engine.actions import ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))
    monkeypatch.setenv("MYT_ENABLE_RPC", "0")
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    scrape_one = Runner().run(
        {
            "task": "blogger_scrape",
            "device_ip": "192.168.1.2",
            "source_key": "k1",
            "pool_key": "pool",
            "counter_key": "count",
            "username": "u1",
            "display_name": "U1",
        }
    )
    scrape_two = Runner().run(
        {
            "task": "blogger_scrape",
            "device_ip": "192.168.1.2",
            "source_key": "k2",
            "pool_key": "pool",
            "counter_key": "count",
            "username": "u1",
            "display_name": "U1",
        }
    )

    assert scrape_one["status"] == "success"
    assert scrape_two["status"] == "success"

    clone = Runner().run({"task": "profile_clone", "device_ip": "192.168.1.2", "source_key": "k2"})
    assert clone["status"] == "success"

    store_path = tmp_path / "config" / "data" / "migration_shared.json"
    payload = store_path.read_text(encoding="utf-8")
    assert "device:192.168.1.2:k2" in payload
    assert "device:192.168.1.2:pool" in payload
    assert "device:192.168.1.2:count" in payload


def test_blogger_scrape_runtime_search_path(monkeypatch, tmp_path):
    from engine.actions import state_actions, ui_actions
    from engine.models.runtime import ActionResult

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    class FakeRpc:
        def __init__(self):
            self.page = 0

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
                      <node text="Second User @second_handle 現金配布" class="android.widget.TextView" package="com.twitter.android" bounds="[50,450][900,520]"/>
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
            _ = (finger_id, x0, y0, x1, y1, duration)
            self.page += 1
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(state_actions.time, "sleep", lambda *_: None)
    monkeypatch.setattr(ui_actions, "app_ensure_running", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "exec_command", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "selector_click_one", lambda params, context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(ui_actions, "input_text", lambda params, context: ActionResult(ok=True, code="ok"))

    scrape = Runner().run(
        {
            "task": "blogger_scrape",
            "device_ip": "192.168.1.2",
            "source_key": "runtime_k1",
            "pool_key": "runtime_pool",
            "counter_key": "runtime_count",
            "ai_type": "part_time",
        }
    )
    assert scrape["status"] == "success"

    clone = Runner().run({"task": "profile_clone", "device_ip": "192.168.1.2", "source_key": "runtime_k1"})
    assert clone["status"] == "success"

    store_path = tmp_path / "config" / "data" / "migration_shared.json"
    payload = store_path.read_text(encoding="utf-8")
    assert "demo_handle" in payload
    assert "second_handle" in payload
