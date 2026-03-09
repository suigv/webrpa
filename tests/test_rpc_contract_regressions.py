# pyright: reportMissingImports=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportIncompatibleMethodOverride=false, reportImplicitOverride=false
import importlib
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from api.server import app
from engine.actions import _rpc_bootstrap


def _load_ui_actions_module() -> Any:
    return importlib.import_module("engine.actions.ui_actions")


def _load_state_actions_module() -> Any:
    return importlib.import_module("engine.actions.state_actions")


def _load_execution_context() -> Any:
    return importlib.import_module("engine.models.runtime").ExecutionContext


class _RecordingRpc:
    init_calls: list[tuple[str, int, int]]
    closed: bool

    def __init__(self) -> None:
        self.init_calls = []
        self.closed = False

    def init(self, ip: str, port: int, timeout: int) -> bool:
        self.init_calls.append((ip, port, timeout))
        return True

    def close(self) -> None:
        self.closed = True


class _FailingRpc(_RecordingRpc):
    def init(self, ip: str, port: int, timeout: int) -> bool:
        self.init_calls.append((ip, port, timeout))
        return False


def test_rpc_bootstrap_resolves_target_rpa_port_before_port_calculation() -> None:
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(
        payload={
            "device_ip": "192.168.1.214",
            "cloud_index": 7,
            "cloud_machines_per_device": 10,
            "_target": {"device_id": 2, "cloud_id": 3, "rpa_port": 30902},
        }
    )

    device_ip, rpa_port = _rpc_bootstrap.resolve_connection_params({}, ctx)

    assert device_ip == "192.168.1.214"
    assert rpa_port == 30902


def test_rpc_bootstrap_uses_session_defaults_before_raw_payload_fallback() -> None:
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(
        payload={
            "device_ip": "192.168.1.214",
            "cloud_index": 7,
            "device_index": 8,
            "cloud_machines_per_device": 10,
        },
        session={
            "defaults": {
                "device_ip": "192.168.1.215",
                "cloud_index": 3,
                "device_index": 2,
                "cloud_machines_per_device": 4,
            }
        },
    )

    device_ip, rpa_port = _rpc_bootstrap.resolve_connection_params({}, ctx)

    assert device_ip == "192.168.1.215"
    assert rpa_port == 30202


def test_rpc_bootstrap_explicit_params_override_session_defaults() -> None:
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214", "cloud_index": 7, "device_index": 8},
        session={"defaults": {"device_ip": "192.168.1.215", "rpa_port": 30202, "cloud_index": 3, "device_index": 2}},
    )

    device_ip, rpa_port = _rpc_bootstrap.resolve_connection_params(
        {"device_ip": "192.168.1.216", "rpa_port": 30502, "cloud_index": 5, "device_index": 6},
        ctx,
    )

    assert device_ip == "192.168.1.216"
    assert rpa_port == 30502


def test_ui_and_state_bootstrap_wrappers_share_connect_timeout_contract(monkeypatch: MonkeyPatch) -> None:
    ui_actions = _load_ui_actions_module()
    state_actions = _load_state_actions_module()
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "cloud_index": 1, "cloud_machines_per_device": 2})

    ui_rpc = _RecordingRpc()
    state_rpc = _RecordingRpc()

    monkeypatch.setattr(ui_actions, "MytRpc", lambda: ui_rpc)
    monkeypatch.setattr(state_actions, "MytRpc", lambda: state_rpc)

    ui_client, ui_error = ui_actions._get_rpc({"connect_timeout": 9}, ctx)
    state_client, state_error = state_actions._connect_rpc({"connect_timeout": 11}, ctx)

    assert ui_error is None
    assert state_error is None
    assert ui_client is ui_rpc
    assert state_client is state_rpc
    assert ui_rpc.init_calls == [("192.168.1.214", 30002, 9)]
    assert state_rpc.init_calls == [("192.168.1.214", 30002, 11)]

    ui_actions._close_rpc(ui_client)
    state_actions._close_rpc(state_client)
    assert ui_rpc.closed is True
    assert state_rpc.closed is True


def test_bootstrap_rpc_surfaces_shared_connect_failure_contract() -> None:
    ExecutionContext = _load_execution_context()
    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214"})

    rpc, error = _rpc_bootstrap.bootstrap_rpc(
        {"rpa_port": 30002, "connect_timeout": 4},
        ctx,
        is_enabled=lambda: True,
        resolve_params=_rpc_bootstrap.resolve_connection_params,
        rpc_factory=_FailingRpc,
    )

    assert rpc is None
    assert error is not None
    assert error.ok is False
    assert error.code == "rpc_connect_failed"
    assert error.message == "connect failed: 192.168.1.214:30002"


def test_health_endpoint_reports_rpc_disabled_flag(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("MYT_ENABLE_RPC", "0")

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["rpc_enabled"] is False
