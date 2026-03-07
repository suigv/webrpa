import importlib


def _load_action_registry_module():
    for name in ("engine.action_registry", "engine.action_registry"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import action_registry module")


def _load_execution_context():
    for name in ("engine.models.runtime", "engine.models.runtime"):
        try:
            return importlib.import_module(name).ExecutionContext
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("cannot import ExecutionContext")


def test_registry_contains_sdk_and_mytos_actions(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()
    assert reg.has("sdk.get_device_info")
    assert reg.has("sdk.start_android")
    assert reg.has("mytos.query_s5_proxy")
    assert reg.has("mytos.set_clipboard")
    assert reg.has("core.generate_totp")
    assert reg.has("core.load_shared_optional")
    assert reg.has("core.append_shared_unique")
    assert reg.has("core.increment_shared_counter")
    assert reg.has("core.resolve_first_non_empty")
    assert reg.has("core.load_ui_value")
    assert reg.has("core.load_ui_selector")
    assert reg.has("core.load_ui_scheme")
    assert reg.has("core.check_daily_limit")
    assert reg.has("core.increment_daily_counter")
    assert reg.has("core.pick_weighted_keyword")
    assert reg.has("core.pick_candidate")
    assert reg.has("core.plan_follow_rounds")
    assert reg.has("core.is_text_blacklisted")
    assert reg.has("core.choose_blogger_search_query")
    assert reg.has("core.derive_blogger_profile")
    assert reg.has("core.save_blogger_candidates")
    assert reg.has("core.save_blogger_candidate")
    assert reg.has("core.get_blogger_candidate")
    assert reg.has("core.mark_processed")
    assert reg.has("core.check_processed")
    assert reg.has("core.collect_blogger_candidates")
    assert reg.has("core.open_candidate")
    assert reg.has("core.generate_dm_reply")
    assert reg.has("core.generate_quote_text")
    assert reg.has("core.extract_dm_last_message")
    assert reg.has("core.extract_dm_last_outbound_message")
    assert reg.has("core.extract_unread_dm_targets")
    assert reg.has("core.open_first_unread_dm")
    assert reg.has("core.extract_follow_targets")
    assert reg.has("core.follow_visible_targets")
    assert reg.has("mytos.upload_google_cert")
    assert reg.has("mytos.set_language_country")
    assert reg.has("mytos.touch_down")
    assert reg.has("mytos.backup_app_info")
    assert reg.has("mytos.query_background_keepalive")
    assert reg.has("sdk.create_android")
    assert reg.has("sdk.list_backups")
    assert reg.has("sdk.list_vpc_groups")
    assert reg.has("sdk.start_lm_server")
    assert reg.has("sdk.get_ssh_ws_url")
    assert reg.has("sdk.open_container_exec")
    assert reg.has("sdk.get_container_exec_ws_url")


def test_sdk_action_invocation_maps_to_client(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip
            self.sdk_port = sdk_port

        def get_device_info(self):
            return {"ok": True, "data": {"ip": self.device_ip, "port": self.sdk_port}}

        def set_clipboard(self, content: str):
            return {"ok": True, "data": {"content": content}}

        def ip_geolocation(self, ip: str, language: str = ""):
            return {"ok": True, "data": {"ip": ip, "language": language}}

        def set_language_country(self, language: str, country: str):
            return {"ok": True, "data": {"language": language, "country": country}}

        def auto_click(self, enabled: bool | None = None, interval_ms: int | None = None, **kwargs):
            return {"ok": True, "data": {"enabled": enabled, "interval_ms": interval_ms, **kwargs}}

        def backup_app_info(self, package: str, save_to: str = ""):
            return {"ok": True, "data": {"package": package, "save_to": save_to}}

        def query_background_keepalive(self):
            return {"ok": True, "data": {"packages": ["com.demo"]}}

        def create_android(self, payload: dict):
            return {"ok": True, "data": payload}

        def list_backups(self, name: str = ""):
            return {"ok": True, "data": {"name": name, "items": []}}

        def set_lm_work_mode(self, mode: str):
            return {"ok": True, "data": {"mode": mode}}

        def get_ssh_ws_url(self, **query):
            return {"ok": True, "data": {"url": "ws://x", "query": query}}

        def open_container_exec(self, **query):
            return {"ok": True, "data": {"query": query}}

        def get_container_exec_ws_url(self, **query):
            return {"ok": True, "data": {"url": "ws://y", "query": query}}

    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    monkeypatch.setattr(sdk_mod, "MytSdkClient", FakeClient)

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.8", "sdk_port": 8010})
    res1 = reg.resolve("sdk.get_device_info")({}, ctx)
    assert res1.ok is True
    assert res1.data["result"]["data"]["ip"] == "192.168.1.8"

    res2 = reg.resolve("mytos.set_clipboard")({"content": "abc"}, ctx)
    assert res2.ok is True
    assert res2.data["result"]["data"]["content"] == "abc"

    res3 = reg.resolve("mytos.ip_geolocation")({"ip": "23.247.138.215", "language": "en"}, ctx)
    assert res3.ok is True
    assert res3.data["result"]["data"]["ip"] == "23.247.138.215"

    res4 = reg.resolve("mytos.set_language_country")({"language": "en", "country": "US"}, ctx)
    assert res4.ok is True
    assert res4.data["result"]["data"]["country"] == "US"

    res4b = reg.resolve("mytos.touch_down")({"x": 12, "y": 34, "finger_id": 2}, ctx)
    assert res4b.ok is True
    assert res4b.data["result"]["data"]["action"] == "down"
    assert res4b.data["result"]["data"]["finger_id"] == 2

    res4c = reg.resolve("mytos.backup_app_info")({"package": "com.demo", "save_to": "/tmp/demo.bak"}, ctx)
    assert res4c.ok is True
    assert res4c.data["result"]["data"]["save_to"] == "/tmp/demo.bak"

    res4d = reg.resolve("mytos.query_background_keepalive")({}, ctx)
    assert res4d.ok is True
    assert res4d.data["result"]["data"]["packages"] == ["com.demo"]

    res5 = reg.resolve("sdk.create_android")({"name": "a-01", "imageUrl": "repo/a:v1", "dns": "223.5.5.5"}, ctx)
    assert res5.ok is True
    assert res5.data["result"]["data"]["name"] == "a-01"

    res5b = reg.resolve("sdk.list_backups")({}, ctx)
    assert res5b.ok is True
    assert res5b.data["result"]["data"]["items"] == []

    res6 = reg.resolve("sdk.set_lm_work_mode")({"mode": "performance"}, ctx)
    assert res6.ok is True
    assert res6.data["result"]["data"]["mode"] == "performance"

    res7 = reg.resolve("sdk.get_ssh_ws_url")({"username": "root"}, ctx)
    assert res7.ok is True
    assert res7.data["result"]["data"]["query"]["username"] == "root"

    res8 = reg.resolve("sdk.open_container_exec")({"name": "a-01"}, ctx)
    assert res8.ok is True
    assert res8.data["result"]["data"]["query"]["name"] == "a-01"

    res9 = reg.resolve("sdk.get_container_exec_ws_url")({"name": "a-01"}, ctx)
    assert res9.ok is True
    assert res9.data["result"]["data"]["query"]["name"] == "a-01"


def test_core_generate_totp_action_returns_6_digits(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={})
    res = reg.resolve("core.generate_totp")({"secret": "JBSWY3DPEHPK3PXP"}, ctx)
    assert res.ok is True
    token = str(res.data.get("token", ""))
    assert len(token) == 6
    assert token.isdigit()


def test_sdk_wait_cloud_status_action_polls_until_target(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    class FakeClient:
        def __init__(self, device_ip: str, sdk_port: int = 8000, timeout_seconds: float = 30.0, retries: int = 3):
            self.device_ip = device_ip
            self.statuses = ["stopped", "booting", "running"]

        def get_cloud_status(self, name: str):
            return {"ok": True, "data": {"name": name, "status": self.statuses.pop(0)}}

    sdk_mod = importlib.import_module("engine.actions.sdk_actions")
    monkeypatch.setattr(sdk_mod, "MytSdkClient", FakeClient)

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.8", "sdk_port": 8010})
    res = reg.resolve("sdk.wait_cloud_status")(
        {"name": "android-01", "target_status": "running", "timeout_ms": 1000, "interval_ms": 10},
        ctx,
    )
    assert res.ok is True
    assert res.data["status"] == "running"


def test_core_shared_state_actions_support_scope_and_unique_append(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.8", "_task_id": "task-1"})

    save = reg.resolve("core.save_shared")(
        {"key": "latest", "scope": "device", "value": {"username": "u1"}},
        ctx,
    )
    assert save.ok is True
    assert save.data["key"] == "device:192.168.1.8:latest"

    load = reg.resolve("core.load_shared_required")({"key": "latest", "scope": "device"}, ctx)
    assert load.ok is True
    assert load.data["value"]["username"] == "u1"

    opt_missing = reg.resolve("core.load_shared_optional")(
        {"key": "missing", "scope": "task", "default": []},
        ctx,
    )
    assert opt_missing.ok is True
    assert opt_missing.data["exists"] is False
    assert opt_missing.data["value"] == []

    add_one = reg.resolve("core.append_shared_unique")(
        {
            "key": "pool",
            "scope": "device",
            "identity_field": "username",
            "item": {"username": "u1", "display_name": "User 1"},
        },
        ctx,
    )
    add_two = reg.resolve("core.append_shared_unique")(
        {
            "key": "pool",
            "scope": "device",
            "identity_field": "username",
            "item": {"username": "u1", "display_name": "User 1 newer"},
        },
        ctx,
    )
    assert add_one.ok is True
    assert add_one.data["added"] is True
    assert add_two.ok is True
    assert add_two.data["added"] is False
    assert add_two.data["size"] == 1


def test_core_ui_config_actions_load_selector_and_scheme_with_repo_fallback(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={})

    package_value = reg.resolve("core.load_ui_value")({"key": "package_name"}, ctx)
    assert package_value.ok is True
    assert package_value.data["value"] == "com.twitter.android"

    selector = reg.resolve("core.load_ui_selector")({"key": "login.input_user"}, ctx)
    assert selector.ok is True
    assert selector.data["type"] == "id"
    assert selector.data["value"] == "com.twitter.android:id/ocf_text_input_edit"

    scheme = reg.resolve("core.load_ui_scheme")(
        {"key": "profile", "kwargs": {"screen_name": "user name"}},
        ctx,
    )
    assert scheme.ok is True
    assert scheme.data["url"] == "twitter://user?screen_name=user%20name"
    assert "android.intent.action.VIEW" in scheme.data["command"]

    counter = reg.resolve("core.increment_shared_counter")(
        {"key": "scrape_count", "scope": "task", "amount": 2, "start": 0},
        ctx,
    )
    assert counter.ok is True
    assert counter.data["value"] == 2

    resolved = reg.resolve("core.resolve_first_non_empty")({"values": ["", " value ", None]}, ctx)
    assert resolved.ok is True
    assert resolved.data["value"] == "value"


def test_core_nurture_strategy_and_blacklist_actions(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.8"})

    keyword = reg.resolve("core.pick_weighted_keyword")({"ai_type": "volc", "blogger": "demo_user"}, ctx)
    assert keyword.ok is True
    assert keyword.data["rendered_keyword"]

    blacklist_hit = reg.resolve("core.is_text_blacklisted")({"ai_type": "part_time", "text": "これは副業案件です"}, ctx)
    assert blacklist_hit.ok is True
    assert blacklist_hit.data["contains"] is True
    assert blacklist_hit.data["matched"] == "副業"


def test_core_blogger_and_processed_actions(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.8"})

    save_candidate = reg.resolve("core.save_blogger_candidate")(
        {
            "key": "pool",
            "scope": "device",
            "candidate": {"username": "demo", "display_name": "Demo"},
        },
        ctx,
    )
    assert save_candidate.ok is True
    assert save_candidate.data["size"] == 1

    load_candidate = reg.resolve("core.get_blogger_candidate")({"key": "pool", "scope": "device", "index": 0}, ctx)
    assert load_candidate.ok is True
    assert load_candidate.data["candidate"]["username"] == "demo"

    save_many = reg.resolve("core.save_blogger_candidates")(
        {
            "key": "pool",
            "scope": "device",
            "candidates": [
                {"text": "Demo User @demo_one PayPay 配布"},
                {"text": "Second User @second_handle 現金配布"},
            ],
        },
        ctx,
    )
    assert save_many.ok is True
    assert save_many.data["added_count"] == 2

    load_second = reg.resolve("core.get_blogger_candidate")({"key": "pool", "scope": "device", "index": 2}, ctx)
    assert load_second.ok is True
    assert load_second.data["candidate"]["username"] == "second_handle"

    mark = reg.resolve("core.mark_processed")({"key": "quoted", "scope": "device", "item": "https://x.com/demo/status/1"}, ctx)
    assert mark.ok is True

    check = reg.resolve("core.check_processed")({"key": "quoted", "scope": "device", "item": "https://x.com/demo/status/1"}, ctx)
    assert check.ok is True
    assert check.data["contains"] is True


def test_core_pick_candidate_prefers_target_content(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={})
    result = reg.resolve("core.pick_candidate")(
        {
            "ai_type": "part_time",
            "candidates": [
                {"text": "副業案件です", "desc": "", "has_media": False},
                {"text": "PayPay 配布 5000円", "desc": "", "has_media": False},
                {"text": "雑谈", "desc": "", "has_media": True},
            ],
        },
        ctx,
    )
    assert result.ok is True
    assert "PayPay" in result.data["candidate"]["text"]


def test_core_choose_blogger_query_and_derive_profile(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={})
    query = reg.resolve("core.choose_blogger_search_query")({"ai_type": "part_time"}, ctx)
    assert query.ok is True
    assert query.data["query"] == "#mytjz"

    derived = reg.resolve("core.derive_blogger_profile")(
        {
            "candidate": {
                "text": "Demo User @demo_handle PayPay 配布",
                "desc": "PayPay 配布 5000円",
            }
        },
        ctx,
    )
    assert derived.ok is True
    assert derived.data["username"] == "demo_handle"
    assert derived.data["display_name"] == "Demo User"


def test_core_generate_interaction_text_actions(monkeypatch, tmp_path):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    monkeypatch.setenv("MYT_NEW_ROOT", str(tmp_path))

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={})
    dm = reg.resolve("core.generate_dm_reply")({"ai_type": "part_time", "last_message": "对方说 hello"}, ctx)
    assert dm.ok is True
    assert dm.data["reply_text"]

    quote = reg.resolve("core.generate_quote_text")({"ai_type": "volc", "source_text": "这是原文"}, ctx)
    assert quote.ok is True
    assert quote.data["quote_text"]


def test_core_plan_follow_rounds(monkeypatch):
    mod = _load_action_registry_module()
    ActionRegistry = mod.ActionRegistry
    register_defaults = mod.register_defaults
    ExecutionContext = _load_execution_context()

    reg = ActionRegistry()
    monkeypatch.setattr(mod, "_registry", reg)
    register_defaults()

    ctx = ExecutionContext(payload={})
    planned = reg.resolve("core.plan_follow_rounds")({"target_follow_count": 5}, ctx)
    assert planned.ok is True
    assert planned.data["round_one"] == 3
    assert planned.data["round_two"] == 2
