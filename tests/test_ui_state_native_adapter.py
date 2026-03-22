# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false

from typing import cast, final

import pytest
from _pytest.monkeypatch import MonkeyPatch

from engine.actions import state_actions
from engine.models.runtime import ActionResult, ExecutionCancelled, ExecutionContext
from engine.ui_state_native_adapter import NativeUIStateAdapter
from engine.ui_state_native_bindings import NativeStateProfile


def test_native_adapter_login_stage_match_returns_structured_evidence(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeRpc:
        query_text: str

        def __init__(self):
            self.query_text = ""

        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def exec_cmd(self, command: object) -> tuple[str, bool]:
            _ = command
            return "", True

        def create_selector(self) -> int:
            return 1

        def clear_selector(self, selector: object) -> bool:
            _ = selector
            return True

        def addQuery_TextContainWith(self, selector: object, value: object) -> bool:
            _ = selector
            self.query_text = str(value)
            return True

        def addQuery_DescContainWith(self, selector: object, value: object) -> bool:
            _ = (selector, value)
            return True

        def execQueryOne(self, selector: object) -> int | None:
            _ = selector
            return 1 if self.query_text == "账号" else None

        def free_selector(self, selector: object) -> bool:
            _ = selector
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    # Architecture 2.0: pass stage_patterns explicitly via action_params.
    # The global YAML no longer contains locale text — patterns are app/task-specific.
    service = NativeUIStateAdapter(
        action_params={
            "stage_patterns": {"account": {"text_markers": ["账号"]}},
            "stage_order": ["account"],
        }
    )
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = service.match_state(ctx, expected_state_ids=["home", "account"])

    assert result.ok is True
    assert result.status == "matched"
    assert result.platform == "native"
    assert result.state.state_id == "account"
    assert result.evidence.summary == "matched native login stage 'account'"
    assert result.evidence.text == "account"
    assert result.evidence.matched == ["account"]
    assert result.evidence.missing == ["home"]
    assert result.raw_details["stage"] == "account"
    assert result.raw_details["state_profile_id"] == "login_stage"
    assert result.raw_details["state_profile_name"] == "login"
    assert result.raw_details["target_stages"] == ["account", "home"]
    assert result.raw_details["supported_state_ids"] == [
        "home",
        "two_factor",
        "captcha",
        "password",
        "account",
        "login_entry",
        "unknown",
    ]
    assert result.timing.attempt == 1
    assert result.timing.samples == 1


def test_native_adapter_login_stage_no_match_preserves_evidence(monkeypatch: MonkeyPatch) -> None:
    @final
    class FakeRpc:
        query_text: str

        def __init__(self):
            self.query_text = ""

        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def exec_cmd(self, command: object) -> tuple[str, bool]:
            _ = command
            return "", True

        def create_selector(self) -> int:
            return 1

        def clear_selector(self, selector: object) -> bool:
            _ = selector
            return True

        def addQuery_TextContainWith(self, selector: object, value: object) -> bool:
            _ = selector
            self.query_text = str(value)
            return True

        def addQuery_DescContainWith(self, selector: object, value: object) -> bool:
            _ = (selector, value)
            return True

        def execQueryOne(self, selector: object) -> int | None:
            _ = selector
            return 1 if self.query_text == "password" else None

        def free_selector(self, selector: object) -> bool:
            _ = selector
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(
        action_params={
            "stage_patterns": {"password": {"text_markers": ["password"]}},
            "stage_order": ["password"],
        }
    )
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = service.match_state(ctx, expected_state_ids=["home"])

    assert result.ok is False
    assert result.code == "no_match"
    assert result.state.state_id == "password"
    assert result.evidence.summary == "detected native login stage 'password'"
    assert result.evidence.matched == []
    assert result.evidence.missing == ["home"]
    assert result.raw_details["stage"] == "password"


def test_native_adapter_unknown_stage_is_not_authoritative_even_if_expected(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeRpc:
        query_text: str

        def __init__(self):
            self.query_text = ""

        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def exec_cmd(self, command: object) -> tuple[str, bool]:
            _ = command
            return "", True

        def create_selector(self) -> int:
            return 1

        def clear_selector(self, selector: object) -> bool:
            _ = selector
            return True

        def addQuery_TextContainWith(self, selector: object, value: object) -> bool:
            _ = selector
            self.query_text = str(value)
            return True

        def addQuery_DescContainWith(self, selector: object, value: object) -> bool:
            _ = (selector, value)
            return True

        def execQueryOne(self, selector: object) -> int | None:
            _ = selector
            return None

        def free_selector(self, selector: object) -> bool:
            _ = selector
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(
        action_params={
            "stage_patterns": {"account": {"text_markers": ["account"]}},
            "stage_order": ["account"],
        }
    )
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = service.match_state(ctx, expected_state_ids=["home", "unknown"])

    assert result.ok is False
    assert result.code == "no_match"
    assert result.status == "no_match"
    assert result.state.state_id == "unknown"
    assert result.evidence.confidence == 0.0
    assert result.evidence.matched == []


def test_native_adapter_wait_until_timeout_returns_structured_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeClock:
        now: float

        def __init__(self):
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    @final
    class FakeRpc:
        query_text: str

        def __init__(self):
            self.query_text = ""

        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def exec_cmd(self, command: object) -> tuple[str, bool]:
            _ = command
            return "", True

        def create_selector(self) -> int:
            return 1

        def clear_selector(self, selector: object) -> bool:
            _ = selector
            return True

        def addQuery_TextContainWith(self, selector: object, value: object) -> bool:
            _ = selector
            self.query_text = str(value)
            return True

        def addQuery_DescContainWith(self, selector: object, value: object) -> bool:
            _ = (selector, value)
            return True

        def execQueryOne(self, selector: object) -> int | None:
            _ = selector
            return 1 if self.query_text == "password" else None

        def free_selector(self, selector: object) -> bool:
            _ = selector
            return True

    clock = FakeClock()
    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr("engine.actions.state_actions.time.monotonic", clock.monotonic)
    monkeypatch.setattr("engine.actions.state_actions.time.sleep", clock.sleep)
    monkeypatch.setattr("engine.ui_state_native_adapter.time.monotonic", clock.monotonic)

    service = NativeUIStateAdapter(
        action_params={
            "stage_patterns": {"password": {"text_markers": ["password"]}},
            "stage_order": ["password"],
        }
    )
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    result = service.wait_until(ctx, expected_state_ids=["home"], timeout_ms=30, interval_ms=1)

    assert result.ok is False
    assert result.code == "timeout"
    assert result.status == "timeout"
    assert result.state.state_id == "password"
    assert result.message == "wait stage timeout, last stage: password"
    assert result.raw_details["legacy_code"] == "stage_timeout"
    assert result.raw_details["stage"] == "password"
    assert result.raw_details["attempt"] == 1
    assert result.raw_details["elapsed_ms"] == 50
    assert result.raw_details["target_stages"] == ["home"]
    assert result.timing.timeout_ms == 30
    assert result.timing.interval_ms == 1
    assert result.timing.attempt == 1
    assert result.timing.samples == 1
    assert result.evidence.missing == ["home"]


def test_native_adapter_wait_until_cancellation_raises(monkeypatch: MonkeyPatch) -> None:
    wait_calls: list[dict[str, object]] = []

    def _match_action(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"stage": "home"})

    def _wait_action(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = context
        wait_calls.append(params)
        return ActionResult(
            ok=True, code="ok", data={"stage": "home", "attempt": 1, "elapsed_ms": 0}
        )

    def _normalize_state_id(state_id: str) -> str:
        return "home" if state_id == "home" else "unknown"

    def _state_id_from_action_result(result: ActionResult) -> str:
        return cast(str, result.data.get("stage", "unknown"))

    profile = NativeStateProfile(
        state_profile_id="cancel_wait",
        display_name="cancel wait",
        state_noun="stage",
        supported_state_ids=("home",),
        normalize_state_id=_normalize_state_id,
        state_id_from_action_result=_state_id_from_action_result,
        match_action=_match_action,
        wait_action=_wait_action,
    )

    def _resolve_profile(state_profile_id: str) -> NativeStateProfile:
        _ = state_profile_id
        return profile

    monkeypatch.setattr(
        "engine.ui_state_native_adapter.resolve_native_state_profile", _resolve_profile
    )

    service = NativeUIStateAdapter(state_profile_id="cancel_wait")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    cancel_calls = 0

    def _should_cancel() -> bool:
        nonlocal cancel_calls
        cancel_calls += 1
        return cancel_calls >= 3

    ctx.should_cancel = _should_cancel

    with pytest.raises(ExecutionCancelled):
        _ = service.wait_until(ctx, expected_state_ids=["home"], timeout_ms=50, interval_ms=1)

    assert wait_calls
    assert cancel_calls == 3


def test_native_adapter_prefers_state_profile_id_over_binding_id(
    monkeypatch: MonkeyPatch,
) -> None:
    resolved_ids: list[str] = []

    def _match_action(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return ActionResult(ok=True, code="ok", data={"stage": "home"})

    profile = NativeStateProfile(
        state_profile_id="preferred_profile",
        display_name="preferred profile",
        state_noun="stage",
        supported_state_ids=("home",),
        normalize_state_id=lambda state_id: state_id,
        state_id_from_action_result=lambda result: cast(str, result.data.get("stage", "unknown")),
        match_action=_match_action,
    )

    def _resolve_profile(state_profile_id: str) -> NativeStateProfile:
        resolved_ids.append(state_profile_id)
        return profile

    monkeypatch.setattr(
        "engine.ui_state_native_adapter.resolve_native_state_profile", _resolve_profile
    )

    _ = NativeUIStateAdapter(state_profile_id="preferred_profile", binding_id="legacy_binding")

    assert resolved_ids == ["preferred_profile"]


def test_wait_login_stage_cancellation_interrupts_loop(monkeypatch: MonkeyPatch) -> None:
    @final
    class FakeRpc:
        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

    detect_calls = 0

    def _detect_stage(rpc: object, _params: dict[str, object], _context: ExecutionContext) -> str:
        nonlocal detect_calls
        _ = (rpc, _params, _context)
        detect_calls += 1
        return "unknown"

    monkeypatch.setattr(state_actions, "_is_rpc_enabled", lambda: True)
    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)
    monkeypatch.setattr(state_actions, "_detect_login_stage_with_rpc", _detect_stage)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}}
    )
    cancel_calls = 0

    def _should_cancel() -> bool:
        nonlocal cancel_calls
        cancel_calls += 1
        return cancel_calls >= 3

    ctx.should_cancel = _should_cancel

    with pytest.raises(ExecutionCancelled):
        _ = state_actions.wait_login_stage(
            {"timeout_ms": 50, "interval_ms": 1, "target_stages": ["home"]}, ctx
        )

    assert detect_calls == 1
    assert cancel_calls == 3


def test_native_adapter_wait_until_rpc_disabled_returns_structured_error(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(state_actions, "_is_rpc_enabled", lambda: False)

    service = NativeUIStateAdapter()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})
    result = service.wait_until(ctx, expected_state_ids=["home"], timeout_ms=30, interval_ms=1)

    assert result.ok is False
    assert result.code == "rpc_disabled"
    assert result.status == "unknown"
    assert result.message == "MYT_ENABLE_RPC=0"
    assert result.raw_details["error_code"] == "rpc_disabled"
    assert result.raw_details["attempt"] == 0
    assert result.raw_details["target_stages"] == ["home"]
    assert result.timing.attempt == 0
    assert result.timing.samples == 0


def test_native_adapter_wait_until_unavailable_returns_structured_error(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FailingRpc:
        init_calls = 0

        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            type(self).init_calls += 1
            return False

        def close(self) -> None:
            return None

    monkeypatch.setattr(state_actions, "_is_rpc_enabled", lambda: True)
    monkeypatch.setattr(state_actions, "MytRpc", FailingRpc)

    service = NativeUIStateAdapter()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "rpa_port": 30002})
    result = service.wait_until(ctx, expected_state_ids=["home"], timeout_ms=30, interval_ms=1)

    assert result.ok is False
    assert result.code == "rpc_connect_failed"
    assert result.status == "unknown"
    assert result.message == "connect failed: 192.168.1.214:30002"
    assert result.raw_details["error_code"] == "rpc_connect_failed"
    assert result.raw_details["attempt"] == 0
    assert FailingRpc.init_calls == 1


def test_native_adapter_presence_binding_compatibility_treats_missing_as_matched_state(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeRpc:
        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def dump_node_xml_ex(self, work_mode: object, timeout_ms: object) -> str:
            _ = (work_mode, timeout_ms)
            return "<hierarchy />"

        def dump_node_xml(self, dump_all: object) -> str:
            _ = dump_all
            return ""

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(binding_id="dm_last_message")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "package": "com.example.app"})
    result = service.match_state(ctx, expected_state_ids=["available", "missing"])

    assert result.ok is True
    assert result.code == "ok"
    assert result.status == "matched"
    assert result.state.state_id == "missing"
    assert result.message == "no dm message extracted"
    assert result.evidence.matched == ["missing"]
    assert result.raw_details["binding_id"] == "dm_last_message"
    assert result.raw_details["legacy_code"] == "dm_message_missing"


def test_native_adapter_dm_unread_binding_exposes_first_target_alias(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeRpc:
        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def dump_node_xml_ex(self, work_mode: object, timeout_ms: object) -> str:
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.example.app" bounds="[30,500][980,680]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all: object) -> str:
            _ = dump_all
            return ""

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(state_profile_id="dm_unread")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "package": "com.example.app"})
    result = service.match_state(ctx, expected_state_ids=["available", "missing"])
    targets = cast(list[object], result.raw_details["targets"])

    assert result.ok is True
    assert result.state.state_id == "available"
    assert result.raw_details["target"] == targets[0]


def test_native_adapter_timeline_candidates_binding_exposes_first_candidate_alias(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeRpc:
        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def dump_node_xml_ex(self, work_mode: object, timeout_ms: object) -> str:
            _ = (work_mode, timeout_ms)
            return """
            <hierarchy>
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2200]">
                <node text="" resource-id="com.example.app:id/row" class="android.widget.LinearLayout" package="com.example.app" bounds="[0,420][1080,980]">
                  <node text="PayPay 配布 5000円" class="android.widget.TextView" package="com.example.app" bounds="[50,450][900,520]"/>
                </node>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all: object) -> str:
            _ = dump_all
            return ""

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(state_profile_id="timeline_candidates")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "package": "com.example.app"})
    result = service.match_state(ctx, expected_state_ids=["available", "missing"])
    candidates = cast(list[object], result.raw_details["candidates"])

    assert result.ok is True
    assert result.state.state_id == "available"
    assert result.raw_details["candidate"] == candidates[0]
    assert result.raw_details["supported_state_ids"] == ["available", "missing", "unknown"]


def test_native_adapter_follow_targets_binding_treats_missing_as_matched_state(
    monkeypatch: MonkeyPatch,
) -> None:
    @final
    class FakeRpc:
        def init(self, ip: object, port: object, timeout: object) -> bool:
            _ = (ip, port, timeout)
            return True

        def close(self) -> None:
            return None

        def dump_node_xml_ex(self, work_mode: object, timeout_ms: object) -> str:
            _ = (work_mode, timeout_ms)
            return "<hierarchy />"

        def dump_node_xml(self, dump_all: object) -> str:
            _ = dump_all
            return ""

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(state_profile_id="follow_targets")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "package": "com.example.app"})
    result = service.match_state(ctx, expected_state_ids=["available", "missing"])

    assert result.ok is True
    assert result.code == "ok"
    assert result.status == "matched"
    assert result.state.state_id == "missing"
    assert result.message == "no follow targets extracted"
    assert result.raw_details["legacy_code"] == "follow_targets_missing"


def test_ui_match_state_uses_injected_stage_patterns_when_params_absent(monkeypatch: MonkeyPatch) -> None:
    from engine.action_registry import resolve_action

    captured: dict[str, object] = {}

    class FakeAdapter:
        def __init__(self, state_profile_id: str, *, action_params=None, binding_id=None):
            captured["state_profile_id"] = state_profile_id
            captured["binding_id"] = binding_id
            captured["action_params"] = dict(action_params or {})

        def match_state(self, context: ExecutionContext, *, expected_state_ids, timeout_ms=None):
            _ = (context, expected_state_ids, timeout_ms)

            class _Result:
                def to_action_result(self):
                    return ActionResult(ok=True, code="ok", data={"state": {"state_id": "home"}})

            return _Result()

    monkeypatch.setattr("engine.actions.ui_state_actions.NativeUIStateAdapter", FakeAdapter)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214"},
        session={
            "defaults": {
                "package": "com.twitter.android",
                "_app_stage_patterns": {"home": {"text_markers": ["For you"]}},
                "_app_selectors": {"home_tab": {"type": "id", "value": "home"}},
            }
        },
    )
    result = resolve_action("ui.match_state")(
        {
            "platform": "native",
            "state_profile_id": "app_stage",
            "expected_state_ids": ["home"],
        },
        ctx,
    )

    assert result.ok is True
    assert captured["state_profile_id"] == "app_stage"
    assert captured["binding_id"] is None
    action_params = cast(dict[str, object], captured["action_params"])
    assert action_params["package"] == "com.twitter.android"
    assert action_params["stage_patterns"] == {
        "home": {"text_markers": ["For you"]}
    }
    assert action_params["_app_stage_patterns"] == {
        "home": {"text_markers": ["For you"]}
    }
    assert action_params["_app_selectors"] == {
        "home_tab": {"type": "id", "value": "home"}
    }
