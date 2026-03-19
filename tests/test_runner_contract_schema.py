from core.task_execution import ActiveTargetCircuitBreaker
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


def test_target_circuit_breaker_can_be_disabled():
    breaker = ActiveTargetCircuitBreaker(
        task_id="task-1",
        target={"device_id": 1, "cloud_id": 12},
        enabled=False,
    )

    assert breaker.should_cancel() is False
    assert breaker.trip() is None


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
