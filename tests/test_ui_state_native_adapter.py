# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false

from typing import Optional, cast, final

from _pytest.monkeypatch import MonkeyPatch

from engine.actions import state_actions
from engine.models.runtime import ExecutionContext
from engine.ui_state_native_adapter import NativeUIStateAdapter


def test_native_adapter_login_stage_match_returns_structured_evidence(monkeypatch: MonkeyPatch) -> None:
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

        def execQueryOne(self, selector: object) -> Optional[int]:
            _ = selector
            return 1 if self.query_text == "已有账号" else None

        def free_selector(self, selector: object) -> bool:
            _ = selector
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}})
    result = service.match_state(ctx, expected_state_ids=["home", "account"])

    assert result.ok is True
    assert result.status == "matched"
    assert result.platform == "native"
    assert result.state.state_id == "account"
    assert result.evidence.summary == "matched native X login stage 'account'"
    assert result.evidence.text == "account"
    assert result.evidence.matched == ["account"]
    assert result.evidence.missing == ["home"]
    assert result.raw_details["stage"] == "account"
    assert result.raw_details["target_stages"] == ["account", "home"]
    assert result.raw_details["supported_state_ids"] == ["home", "two_factor", "captcha", "password", "account", "unknown"]
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

        def execQueryOne(self, selector: object) -> Optional[int]:
            _ = selector
            return 1 if self.query_text == "password" else None

        def free_selector(self, selector: object) -> bool:
            _ = selector
            return True

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}})
    result = service.match_state(ctx, expected_state_ids=["home"])

    assert result.ok is False
    assert result.code == "no_match"
    assert result.state.state_id == "password"
    assert result.evidence.summary == "detected native X login stage 'password'"
    assert result.evidence.matched == []
    assert result.evidence.missing == ["home"]
    assert result.raw_details["stage"] == "password"


def test_native_adapter_wait_until_timeout_returns_structured_timeout(monkeypatch: MonkeyPatch) -> None:
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

        def execQueryOne(self, selector: object) -> Optional[int]:
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

    service = NativeUIStateAdapter()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "_target": {"device_id": 1, "cloud_id": 3}})
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


def test_native_adapter_wait_until_rpc_disabled_returns_structured_error(monkeypatch: MonkeyPatch) -> None:
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


def test_native_adapter_wait_until_unavailable_returns_structured_error(monkeypatch: MonkeyPatch) -> None:
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


def test_native_adapter_presence_binding_treats_missing_as_matched_state(monkeypatch: MonkeyPatch) -> None:
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
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "package": "com.twitter.android"})
    result = service.match_state(ctx, expected_state_ids=["available", "missing"])

    assert result.ok is True
    assert result.code == "ok"
    assert result.status == "matched"
    assert result.state.state_id == "missing"
    assert result.message == "no dm message extracted"
    assert result.evidence.matched == ["missing"]
    assert result.raw_details["legacy_code"] == "dm_message_missing"


def test_native_adapter_dm_unread_binding_exposes_first_target_alias(monkeypatch: MonkeyPatch) -> None:
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
              <node text="" resource-id="" class="android.widget.FrameLayout" package="com.twitter.android" bounds="[0,0][1080,2200]">
                <node text="未読 1" content-desc="Unread conversation" class="android.view.View" package="com.twitter.android" bounds="[30,500][980,680]"/>
              </node>
            </hierarchy>
            """

        def dump_node_xml(self, dump_all: object) -> str:
            _ = dump_all
            return ""

    monkeypatch.setattr(state_actions, "MytRpc", FakeRpc)

    service = NativeUIStateAdapter(binding_id="dm_unread")
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "package": "com.twitter.android"})
    result = service.match_state(ctx, expected_state_ids=["available", "missing"])
    targets = cast(list[object], result.raw_details["targets"])

    assert result.ok is True
    assert result.state.state_id == "available"
    assert result.raw_details["target"] == targets[0]
