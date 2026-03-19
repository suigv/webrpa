from datetime import UTC, datetime, timedelta

from core.task_execution import (
    ActiveTargetCircuitBreaker,
    _build_confirmed_target_trip,
    _build_target_trip,
)
from engine.models.manifest import InputType, PluginInput
from engine.models.runtime import ActionResult
from engine.models.workflow import ActionStep, StopStep, WorkflowScript
from engine.parser import parse_script
from engine.runner import Runner


def test_runner_unsupported_task_returns_controlled_error():
    result = Runner().run({"task": "some_unknown_task"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert "message" in result
    assert "timestamp" in result


def test_anonymous_task_stays_backward_compatible():
    result = Runner().run({"task": "anonymous", "steps": []})
    assert result["ok"] is True
    assert result["status"] == "stub_executed"


def test_one_click_new_device_actions_are_allowed():
    runner = Runner()
    plugin = runner._plugin_loader.get("one_click_new_device")

    assert plugin is not None
    script = parse_script(plugin.script_path)

    assert runner._validate_script_actions(script) is None


def test_interpreter_interpolates_plugin_input_defaults(monkeypatch):
    import engine.interpreter as interpreter_module

    seen: dict[str, object] = {}

    def _fake_dispatch_action(action, params, context, registry=None):
        _ = (action, context, registry)
        seen.update(params)
        return ActionResult(ok=True, code="ok", data={"params": params})

    monkeypatch.setattr(interpreter_module, "dispatch_action", _fake_dispatch_action)

    script = WorkflowScript(
        version="v1",
        workflow="defaults_probe",
        steps=[
            ActionStep(
                kind="action",
                action="profile.apply_env_bundle",
                params={
                    "text_value": "${payload.optional_text}",
                    "bool_value": "${payload.optional_flag}",
                },
            )
        ],
    )

    result = interpreter_module.Interpreter().execute(
        script,
        payload={},
        plugin_inputs=[
            PluginInput(name="optional_text", type=InputType.string, default=""),
            PluginInput(name="optional_flag", type=InputType.boolean, default=False),
        ],
    )

    assert result["ok"] is True
    assert seen["text_value"] == ""
    assert seen["bool_value"] is False


def test_interpreter_session_defaults_keep_legacy_payload_device_ip_fallback():
    import engine.interpreter as interpreter_module

    defaults = interpreter_module.Interpreter()._build_session_defaults(
        payload={"device_ip": "192.168.1.214"},
        plugin_inputs=[],
        runtime={"target": {"device_id": 2, "cloud_id": 3}},
    )

    assert defaults["device_ip"] == "192.168.1.214"
    assert defaults["cloud_index"] == 3
    assert defaults["device_index"] == 2


def test_target_circuit_breaker_can_be_disabled():
    breaker = ActiveTargetCircuitBreaker(
        task_id="task-1",
        target={"device_id": 1, "cloud_id": 12},
        enabled=False,
    )

    assert breaker.should_cancel() is False
    assert breaker.trip() is None


def test_build_target_trip_ignores_probe_snapshot_before_activation():
    before_activation = datetime.now(UTC) - timedelta(seconds=2)
    snapshot = {
        "availability_state": "unavailable",
        "availability_reason": "timed out",
        "last_checked_at": before_activation.isoformat(),
        "latency_ms": 803,
        "stale": False,
    }

    trip = _build_target_trip(
        device_id=1,
        cloud_id=1,
        snapshot=snapshot,
        min_last_checked_at_epoch=datetime.now(UTC).timestamp(),
    )

    assert trip is None


def test_build_target_trip_accepts_probe_snapshot_after_activation():
    after_activation = datetime.now(UTC) + timedelta(seconds=1)
    snapshot = {
        "availability_state": "unavailable",
        "availability_reason": "timed out",
        "last_checked_at": after_activation.isoformat(),
        "latency_ms": 803,
        "stale": False,
    }

    trip = _build_target_trip(
        device_id=1,
        cloud_id=1,
        snapshot=snapshot,
        min_last_checked_at_epoch=datetime.now(UTC).timestamp(),
    )

    assert trip is not None
    assert trip.code == "target_unavailable"


def test_build_confirmed_target_trip_ignores_false_unavailable_when_direct_probe_succeeds(
    monkeypatch,
):
    after_activation = datetime.now(UTC) + timedelta(seconds=1)
    snapshot = {
        "availability_state": "unavailable",
        "availability_reason": "[Errno 64] Host is down",
        "last_checked_at": after_activation.isoformat(),
        "latency_ms": 3,
        "stale": False,
    }
    healed: list[tuple[int, int, bool, int | None, str]] = []

    class _Manager:
        def update_cloud_probe(
            self, device_id: int, cloud_id: int, ok: bool, latency_ms: int | None, reason: str
        ) -> None:
            healed.append((device_id, cloud_id, ok, latency_ms, reason))

    monkeypatch.setattr(
        "core.task_execution._probe_target_rpa_port", lambda device_id, cloud_id: (True, 6, "ok")
    )
    monkeypatch.setattr("core.task_execution.get_device_manager", lambda: _Manager())

    trip = _build_confirmed_target_trip(
        device_id=1,
        cloud_id=1,
        snapshot=snapshot,
        min_last_checked_at_epoch=datetime.now(UTC).timestamp(),
    )

    assert trip is None
    assert healed == [(1, 1, True, 6, "ok")]


def test_build_confirmed_target_trip_preserves_failure_when_direct_probe_still_fails(monkeypatch):
    after_activation = datetime.now(UTC) + timedelta(seconds=1)
    snapshot = {
        "availability_state": "unavailable",
        "availability_reason": "[Errno 64] Host is down",
        "last_checked_at": after_activation.isoformat(),
        "latency_ms": 3,
        "stale": False,
    }

    monkeypatch.setattr(
        "core.task_execution._probe_target_rpa_port",
        lambda device_id, cloud_id: (False, 4, "[Errno 64] Host is down"),
    )

    trip = _build_confirmed_target_trip(
        device_id=1,
        cloud_id=1,
        snapshot=snapshot,
        min_last_checked_at_epoch=datetime.now(UTC).timestamp(),
    )

    assert trip is not None
    assert trip.code == "target_unavailable"


def test_interpreter_stop_step_can_return_interpolated_result(monkeypatch):
    import engine.interpreter as interpreter_module

    seen: dict[str, object] = {}

    def _fake_dispatch_action(action, params, context, registry=None):
        _ = (action, context, registry)
        seen.update(params)
        return ActionResult(ok=True, code="ok", data={"current_model": "PKA110"})

    monkeypatch.setattr(interpreter_module, "dispatch_action", _fake_dispatch_action)
    script = WorkflowScript(
        version="v1",
        workflow="summary_probe",
        steps=[
            ActionStep(
                kind="action",
                action="profile.apply_env_bundle",
                params={"model_name": "PKA110"},
                save_as="after_model",
            ),
            StopStep(
                kind="stop",
                status="success",
                message="switched to ${vars.after_model.current_model}",
                result={
                    "report": {
                        "after_model": "${vars.after_model.current_model}",
                        "payload_echo": "${payload.seed}",
                    }
                },
            ),
        ],
    )

    result = interpreter_module.Interpreter().execute(script, payload={"seed": "seed-001"})

    assert seen["model_name"] == "PKA110"
    assert result["ok"] is True
    assert result["message"] == "switched to PKA110"
    assert result["data"]["report"]["after_model"] == "PKA110"
    assert result["data"]["report"]["payload_echo"] == "seed-001"
