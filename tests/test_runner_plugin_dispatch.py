from pathlib import Path
from typing import Any

from new.engine.action_registry import get_registry
from new.engine.models.manifest import PluginManifest
from new.engine.models.runtime import ActionResult
from new.engine.plugin_loader import PluginEntry
from new.engine.runner import Runner


def test_runner_yaml_plugin_dispatch_fails_without_credentials():
    """Runner dispatches x_auto_login to YAML interpreter.
    Without valid credentials_ref, the workflow should fail at credentials.load step.
    """
    result = Runner().run({"task": "x_auto_login"})
    assert result["ok"] is False
    assert result["task"] == "x_auto_login"
    assert "credentials_ref" in result.get("message", "").lower() or "missing" in result.get("message", "").lower()


def test_runner_unknown_plugin_error_is_controlled():
    result = Runner().run({"task": "x_auto_login_missing"})
    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert result["code"] == "unsupported_task"


def test_runner_device_reboot_plugin_dispatch_is_supported():
    result = Runner().run({"task": "device_reboot", "device_ip": "192.168.1.2", "name": "android-01"})
    assert result["task"] == "device_reboot"
    assert "unsupported task" not in str(result.get("message", "")).lower()


def test_runner_device_soft_reset_invalid_payload_is_controlled():
    result = Runner().run({"task": "device_soft_reset", "device_ip": "192.168.1.2"})
    assert result["task"] == "device_soft_reset"
    assert result["status"] in {"failed", "error", "failed_config_error"}
    assert "unsupported task" not in str(result.get("message", "")).lower()


def _make_plugin_entry(tmp_path: Path, manifest_payload: dict[str, Any], script_content: str) -> PluginEntry:
    plugin_dir = tmp_path / manifest_payload["name"]
    plugin_dir.mkdir()
    (plugin_dir / "script.yaml").write_text(script_content, encoding="utf-8")
    manifest = PluginManifest.model_validate(manifest_payload)
    return PluginEntry(manifest=manifest, plugin_dir=plugin_dir)


def test_runner_plugin_missing_required_input_fails_early(tmp_path: Path):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [{"name": "device_ip", "type": "string", "required": True}],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        "version: v1\nworkflow: secure_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
    )
    runner = Runner()
    runner._plugin_loader._plugins = {"secure_plugin": entry}

    result = runner.run({"task": "secure_plugin"})

    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert result["code"] == "missing_required_param"
    assert "device_ip" in result["message"]


def test_runner_plugin_invalid_input_type_fails_early(tmp_path: Path):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [{"name": "device_ip", "type": "string", "required": True}],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        "version: v1\nworkflow: secure_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
    )
    runner = Runner()
    runner._plugin_loader._plugins = {"secure_plugin": entry}

    result = runner.run({"task": "secure_plugin", "device_ip": 123})

    assert result["ok"] is False
    assert result["code"] == "invalid_params"
    assert "expected string" in result["message"]


def test_runner_plugin_unknown_input_fails_early(tmp_path: Path):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [{"name": "device_ip", "type": "string", "required": True}],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        "version: v1\nworkflow: secure_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
    )
    runner = Runner()
    runner._plugin_loader._plugins = {"secure_plugin": entry}

    result = runner.run({"task": "secure_plugin", "device_ip": "192.168.1.2", "unexpected": "x"})

    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert result["code"] == "invalid_params"
    assert "unknown input parameter" in result["message"]
    assert "unexpected" in result["message"]


def test_runner_plugin_task_key_not_treated_as_unknown_input(tmp_path: Path):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [{"name": "device_ip", "type": "string", "required": True}],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        "version: v1\nworkflow: secure_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
    )
    runner = Runner()
    runner._plugin_loader._plugins = {"secure_plugin": entry}

    result = runner.run({"task": "secure_plugin", "device_ip": "192.168.1.2"})

    assert result["ok"] is True
    assert result["status"] == "success"


def test_runner_plugin_unknown_input_check_can_be_disabled_by_env(tmp_path: Path, monkeypatch):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [{"name": "device_ip", "type": "string", "required": True}],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        "version: v1\nworkflow: secure_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
    )
    runner = Runner()
    runner._plugin_loader._plugins = {"secure_plugin": entry}
    monkeypatch.setenv("MYT_STRICT_PLUGIN_UNKNOWN_INPUTS", "0")

    result = runner.run({"task": "secure_plugin", "device_ip": "192.168.1.2", "unexpected": "x"})

    assert result["ok"] is True
    assert result["status"] == "success"


def test_runner_plugin_action_outside_allowed_namespace_is_denied(tmp_path: Path):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        (
            "version: v1\n"
            "workflow: secure_plugin\n"
            "steps:\n"
            "  - kind: action\n"
            "    action: test.noop\n"
            "    params: {}\n"
            "  - kind: stop\n"
            "    status: success\n"
            "    message: ok\n"
        ),
    )
    runner = Runner()
    runner._plugin_loader._plugins = {"secure_plugin": entry}

    registry = get_registry()
    previous_actions = dict(registry._actions)
    registry.register("test.noop", lambda _params, _ctx: ActionResult(ok=True, code="ok"))
    try:
        result = runner.run({"task": "secure_plugin"})
    finally:
        registry._actions = previous_actions

    assert result["ok"] is False
    assert result["status"] == "failed_config_error"
    assert result["checkpoint"] == "dispatch"
    assert result["code"] == "action_not_allowed"
    assert "outside allowed namespaces" in result["message"]
