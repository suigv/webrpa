from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.task_execution import (
    ActiveTargetCircuitBreaker,
    _build_confirmed_target_trip,
    _build_target_trip,
    _probe_target_rpa_port,
    _tolerate_target_unavailable,
)
from engine.models.manifest import InputType, PluginInput
from engine.models.runtime import ActionResult
from engine.models.workflow import ActionStep, StopStep, WorkflowScript
from engine.parser import parse_script
from engine.plugin_loader import clear_shared_plugin_loader_cache, get_shared_plugin_loader
from engine.runner import Runner


def test_runner_unsupported_task_returns_controlled_error():
    result = Runner().run({"task": "some_unknown_task"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert "message" in result
    assert "timestamp" in result


def test_runner_pipeline_executes_repeated_steps_and_emits_progress_events(monkeypatch):
    runner = Runner()
    events: list[tuple[str, dict[str, object]]] = []
    seen_steps: list[str] = []
    sleep_calls: list[float] = []

    def _fake_run_pipeline_step(step, *, should_cancel=None, runtime=None):
        _ = (should_cancel, runtime)
        seen_steps.append(str(step["plugin"]))
        return {
            "ok": True,
            "task": str(step["plugin"]),
            "status": "completed",
            "message": f"{step['label']} done",
        }

    monkeypatch.setattr(runner, "_run_pipeline_step", _fake_run_pipeline_step)
    monkeypatch.setattr("engine.runner.time.sleep", lambda seconds: sleep_calls.append(seconds))

    result = runner.run(
        {
            "task": "_pipeline",
            "steps": [
                {"plugin": "x_scrape_blogger", "label": "采集博主", "payload": {}},
                {"plugin": "x_clone_profile", "label": "克隆资料", "payload": {}},
            ],
            "repeat": 2,
            "repeat_interval_ms": 250,
        },
        runtime={"emit_event": lambda event_type, data: events.append((event_type, dict(data)))},
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["data"]["rounds_completed"] == 2
    assert seen_steps == [
        "x_scrape_blogger",
        "x_clone_profile",
        "x_scrape_blogger",
        "x_clone_profile",
    ]
    assert [event[0] for event in events] == [
        "pipeline.step_done",
        "pipeline.step_done",
        "pipeline.step_done",
        "pipeline.step_done",
    ]
    assert sleep_calls == [0.2, 0.04999999999999999]


def test_runner_pipeline_cancellation_stops_before_next_child_step(monkeypatch):
    runner = Runner()
    calls: list[str] = []
    cancel_state = {"cancelled": False}

    def _fake_run_pipeline_step(step, *, should_cancel=None, runtime=None):
        _ = (runtime,)
        calls.append(str(step["plugin"]))
        cancel_state["cancelled"] = True
        assert should_cancel is not None
        return {
            "ok": True,
            "task": str(step["plugin"]),
            "status": "completed",
            "message": "done",
        }

    monkeypatch.setattr(runner, "_run_pipeline_step", _fake_run_pipeline_step)

    result = runner.run(
        {
            "task": "_pipeline",
            "steps": [
                {"plugin": "x_scrape_blogger", "payload": {}},
                {"plugin": "x_clone_profile", "payload": {}},
            ],
            "repeat": 1,
        },
        should_cancel=lambda: cancel_state["cancelled"],
    )

    assert calls == ["x_scrape_blogger"]
    assert result["ok"] is False
    assert result["status"] == "cancelled"


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


def test_interpreter_session_defaults_expose_injected_hidden_app_defaults():
    import engine.interpreter as interpreter_module

    defaults = interpreter_module.Interpreter()._build_session_defaults(
        payload={
            "package": "com.twitter.android",
            "_app_stage_patterns": {"home": {"text_markers": ["For you"]}},
            "_app_selectors": {"home_tab": {"type": "id", "value": "home"}},
        },
        plugin_inputs=[],
    )

    assert defaults["package"] == "com.twitter.android"
    assert defaults["_app_stage_patterns"] == {"home": {"text_markers": ["For you"]}}
    assert defaults["_app_selectors"] == {"home_tab": {"type": "id", "value": "home"}}


def test_interpreter_applies_speed_scaled_post_action_wait(monkeypatch):
    import engine.interpreter as interpreter_module

    sleeps: list[float] = []

    def _fake_dispatch_action(action, params, context, registry=None):
        _ = (action, params, context, registry)
        return ActionResult(ok=True, code="ok")

    monkeypatch.setattr(interpreter_module, "dispatch_action", _fake_dispatch_action)
    monkeypatch.setattr(interpreter_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    script = WorkflowScript(
        version="v1",
        workflow="wait_probe",
        steps=[
            ActionStep(kind="action", action="ui.click", params={}),
            StopStep(kind="stop", status="success", message="done"),
        ],
    )

    result = interpreter_module.Interpreter().execute(
        script,
        payload={"_speed": "fast", "_wait_min_ms": 100, "_wait_max_ms": 100},
    )

    assert result["ok"] is True
    assert sleeps == [0.05]


def test_interpreter_skips_post_action_wait_for_ui_wait_until_action(monkeypatch):
    import engine.interpreter as interpreter_module

    sleeps: list[float] = []

    def _fake_dispatch_action(action, params, context, registry=None):
        _ = (action, params, context, registry)
        return ActionResult(ok=True, code="ok")

    monkeypatch.setattr(interpreter_module, "dispatch_action", _fake_dispatch_action)
    monkeypatch.setattr(interpreter_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    script = WorkflowScript(
        version="v1",
        workflow="wait_until_probe",
        steps=[
            ActionStep(kind="action", action="ui.wait_until", params={}),
            StopStep(kind="stop", status="success", message="done"),
        ],
    )

    result = interpreter_module.Interpreter().execute(
        script,
        payload={"_speed": "slow", "_wait_min_ms": 100, "_wait_max_ms": 100},
    )

    assert result["ok"] is True
    assert sleeps == []


def test_app_open_uses_injected_package_when_action_param_absent(monkeypatch):
    import engine.actions.ui_app_actions as ui_app_actions
    from engine.models.runtime import ExecutionContext

    class FakeRpc:
        def __init__(self):
            self.opened: list[str] = []

        def openApp(self, package: str) -> bool:
            self.opened.append(package)
            return True

        def close(self) -> None:
            return None

    rpc = FakeRpc()
    monkeypatch.setattr(ui_app_actions, "_get_rpc", lambda params, context: (rpc, None))
    monkeypatch.setattr(ui_app_actions, "_close_rpc", lambda rpc: None)

    ctx = ExecutionContext(
        payload={},
        session={"defaults": {"package": "com.twitter.android"}},
    )
    result = ui_app_actions.app_open({}, ctx)

    assert result.ok is True
    assert rpc.opened == ["com.twitter.android"]


def test_app_open_explicit_package_overrides_injected_default(monkeypatch):
    import engine.actions.ui_app_actions as ui_app_actions
    from engine.models.runtime import ExecutionContext

    class FakeRpc:
        def __init__(self):
            self.opened: list[str] = []

        def openApp(self, package: str) -> bool:
            self.opened.append(package)
            return True

        def close(self) -> None:
            return None

    rpc = FakeRpc()
    monkeypatch.setattr(ui_app_actions, "_get_rpc", lambda params, context: (rpc, None))
    monkeypatch.setattr(ui_app_actions, "_close_rpc", lambda rpc: None)

    ctx = ExecutionContext(
        payload={},
        session={"defaults": {"package": "com.twitter.android"}},
    )
    result = ui_app_actions.app_open({"package": "com.override.app"}, ctx)

    assert result.ok is True
    assert rpc.opened == ["com.override.app"]


def test_target_circuit_breaker_can_be_disabled():
    breaker = ActiveTargetCircuitBreaker(
        task_id="task-1",
        target={"device_id": 1, "cloud_id": 12},
        enabled=False,
    )

    assert breaker.should_cancel() is False
    assert breaker.trip() is None


def test_target_circuit_breaker_requires_available_probe_snapshot(monkeypatch):
    subscribed: list[tuple[int, int]] = []

    class _Manager:
        def get_cloud_probe_snapshot(self, device_id: int, cloud_id: int) -> dict[str, object]:
            return {
                "device_id": device_id,
                "cloud_id": cloud_id,
                "availability_state": "unknown",
                "stale": True,
            }

        def subscribe_cloud_probe(self, device_id: int, cloud_id: int, callback):
            _ = callback
            subscribed.append((device_id, cloud_id))
            return lambda: None

    monkeypatch.setattr("core.system_settings_loader.get_rpc_enabled", lambda: True)
    monkeypatch.setattr("core.task_execution.get_device_manager", lambda: _Manager())

    breaker = ActiveTargetCircuitBreaker(
        task_id="task-1",
        target={"device_id": 1, "cloud_id": 12},
        enabled=True,
    )

    assert breaker.should_cancel() is False
    assert breaker.trip() is None
    assert subscribed == []


def test_tolerate_target_unavailable_uses_plugin_manifest_default():
    assert _tolerate_target_unavailable("device_reboot", {}) is True


def test_runner_does_not_inject_default_app_id_into_plugin_without_declared_input(monkeypatch):
    runner = Runner()
    seen: dict[str, object] = {}

    def _fake_run_yaml_plugin(
        task_name,
        payload,
        plugin,
        should_cancel=None,
        runtime=None,
        emit_event=None,
        *,
        validate_payload=True,
    ):
        _ = (plugin, should_cancel, runtime, emit_event, validate_payload)
        seen.update(payload)
        return {"ok": True, "task": task_name, "status": "completed"}

    monkeypatch.setattr(runner, "_run_yaml_plugin", _fake_run_yaml_plugin)

    result = runner.run({"task": "device_reboot", "timeout_ms": 120000})

    assert result["ok"] is True
    assert seen["timeout_ms"] == 120000
    assert "app_id" not in seen


def test_clear_shared_plugin_loader_cache_rebuilds_future_lookup(tmp_path: Path):
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()

    clear_shared_plugin_loader_cache()
    first = get_shared_plugin_loader(plugins_root=plugins_root)
    clear_shared_plugin_loader_cache()
    second = get_shared_plugin_loader(plugins_root=plugins_root)

    assert first is not second


def test_runner_rechecks_shared_loader_after_cached_miss(monkeypatch):
    class _Loader:
        def __init__(self, entries):
            self._entries = dict(entries)

        def get(self, name: str):
            return self._entries.get(name)

    plugin = type(
        "PluginEntry",
        (),
        {"manifest": type("Manifest", (), {"inputs": []})(), "script_path": Path("/tmp/demo.yaml")},
    )()
    loaders = [_Loader({}), _Loader({}), _Loader({"new_plugin": plugin})]

    calls: list[bool] = []

    def _fake_get_shared_plugin_loader(*, refresh: bool = False):
        calls.append(refresh)
        return loaders.pop(0)

    monkeypatch.setattr("engine.runner.get_shared_plugin_loader", _fake_get_shared_plugin_loader)

    runner = Runner(agent_executor_runtime=None)
    monkeypatch.setattr(
        runner,
        "_run_yaml_plugin",
        lambda *args, **kwargs: {"ok": True, "task": "new_plugin", "status": "completed"},
    )
    monkeypatch.setattr(
        "engine.runner.parse_script",
        lambda path: WorkflowScript(version="v1", workflow="demo", steps=[]),
    )
    monkeypatch.setattr(runner, "_validate_script_actions", lambda script: None)

    result = runner.run({"task": "new_plugin"})

    assert result["ok"] is True
    assert result["task"] == "new_plugin"
    assert calls == [False, False, True]


def test_runner_uses_latest_shared_loader_for_same_named_plugin(monkeypatch):
    class _Loader:
        def __init__(self, entry):
            self._entry = entry

        def get(self, name: str):
            if name != "demo_plugin":
                return None
            return self._entry

    old_plugin = type(
        "PluginEntry",
        (),
        {
            "manifest": type("Manifest", (), {"inputs": [], "version": "old"})(),
            "script_path": Path("/tmp/old.yaml"),
        },
    )()
    new_plugin = type(
        "PluginEntry",
        (),
        {
            "manifest": type("Manifest", (), {"inputs": [], "version": "new"})(),
            "script_path": Path("/tmp/new.yaml"),
        },
    )()
    loaders = [_Loader(old_plugin), _Loader(new_plugin)]

    monkeypatch.setattr(
        "engine.runner.get_shared_plugin_loader",
        lambda *, refresh=False: loaders.pop(0),
    )

    runner = Runner(agent_executor_runtime=None)
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        runner,
        "_run_yaml_plugin",
        lambda task_name, payload, plugin, *args, **kwargs: (
            seen.update({"version": plugin.manifest.version})
            or {"ok": True, "task": task_name, "status": "completed"}
        ),
    )
    monkeypatch.setattr(
        "engine.runner.parse_script",
        lambda path: WorkflowScript(version="v1", workflow="demo", steps=[]),
    )
    monkeypatch.setattr(runner, "_validate_script_actions", lambda script: None)

    result = runner.run({"task": "demo_plugin"})

    assert result["ok"] is True
    assert seen["version"] == "new"


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


def test_probe_target_rpa_port_short_circuits_when_device_ip_missing(monkeypatch):
    monkeypatch.setattr("core.task_execution.get_device_ip", lambda device_id: "")

    def _unexpected_connect(*_args, **_kwargs):
        raise AssertionError("socket probe should not run without a device_ip")

    monkeypatch.setattr("core.task_execution.socket.create_connection", _unexpected_connect)

    ok, latency_ms, reason = _probe_target_rpa_port(1, 1)

    assert ok is False
    assert latency_ms is None
    assert reason == "device_ip_missing"


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
