from pathlib import Path
from typing import Any

import pytest

from engine.action_registry import get_registry
from engine.models.manifest import PluginManifest
from engine.models.runtime import ActionResult, ExecutionContext
from engine.plugin_loader import PluginEntry, PluginLoader, clear_shared_plugin_loader_cache
from engine.runner import Runner


@pytest.fixture(autouse=True)
def reset_shared_plugin_loader_cache():
    clear_shared_plugin_loader_cache()
    yield
    clear_shared_plugin_loader_cache()


def test_runner_yaml_plugin_dispatch_to_mobile_plugin_requires_device_ip():
    """Runner dispatches x_mobile_login to YAML interpreter and enforces manifest inputs."""
    result = Runner().run({"task": "x_mobile_login"})
    assert result["ok"] is False
    assert result["task"] == "x_mobile_login"
    assert "device_ip" in result.get("message", "").lower() or "missing" in result.get("message", "").lower()


def test_runner_unknown_plugin_error_is_controlled():
    result = Runner().run({"task": "removed_plugin_missing"})
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


def _attach_plugin_entry(runner: Runner, tmp_path: Path, entry: PluginEntry) -> None:
    loader = PluginLoader(plugins_root=tmp_path)
    loader._plugins = {entry.manifest.name: entry}
    runner._plugin_loader = loader


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
    _attach_plugin_entry(runner, tmp_path, entry)

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
    _attach_plugin_entry(runner, tmp_path, entry)

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
    _attach_plugin_entry(runner, tmp_path, entry)

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
    _attach_plugin_entry(runner, tmp_path, entry)

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
    _attach_plugin_entry(runner, tmp_path, entry)
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
    _attach_plugin_entry(runner, tmp_path, entry)

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


def test_runner_plugin_manifest_default_package_reaches_action_when_step_omits_it(tmp_path: Path, monkeypatch):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [
            {"name": "device_ip", "type": "string", "required": True},
            {"name": "package", "type": "string", "required": False, "default": "com.demo.app"},
        ],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        (
            "version: v1\n"
            "workflow: secure_plugin\n"
            "steps:\n"
            "  - kind: action\n"
            "    action: app.open\n"
            "    params: {}\n"
            "  - kind: stop\n"
            "    status: success\n"
            "    message: ok\n"
        ),
    )
    runner = Runner()
    _attach_plugin_entry(runner, tmp_path, entry)

    calls: list[tuple[str, int, int]] = []
    packages: list[str] = []

    class _RecordingRpc:
        def init(self, ip: str, port: int, timeout: int) -> bool:
            calls.append((ip, port, timeout))
            return True

        def openApp(self, package: str) -> bool:
            packages.append(package)
            return True

        def close(self) -> None:
            return None

    monkeypatch.setattr("engine.actions.ui_actions.MytRpc", _RecordingRpc)

    result = runner.run({"task": "secure_plugin", "device_ip": "192.168.1.2"})

    assert result["ok"] is True
    assert result["status"] == "success"
    assert calls == [("192.168.1.2", 30002, 5)]
    assert packages == ["com.demo.app"]


def test_runner_plugin_session_defaults_do_not_leak_into_vars_and_explicit_params_win(tmp_path: Path):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [
            {"name": "device_ip", "type": "string", "required": True},
            {"name": "package", "type": "string", "required": False, "default": "com.demo.app"},
        ],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        (
            "version: v1\n"
            "workflow: secure_plugin\n"
            "steps:\n"
            "  - kind: action\n"
            "    action: core.capture_session_default_precedence\n"
            "    params:\n"
            "      package: com.demo.override\n"
            "      device_ip: 10.0.0.8\n"
            "  - kind: stop\n"
            "    status: success\n"
            "    message: ok\n"
        ),
    )
    runner = Runner()
    _attach_plugin_entry(runner, tmp_path, entry)

    captured: dict[str, object] = {}

    def capture_defaults(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        captured["package_param"] = params.get("package")
        captured["device_ip_param"] = params.get("device_ip")
        captured["package_default"] = context.get_session_default("package")
        captured["device_ip_default"] = context.get_session_default("device_ip")
        captured["vars"] = dict(context.vars)
        return ActionResult(ok=True, code="ok")

    get_registry().register("core.capture_session_default_precedence", capture_defaults)

    result = runner.run({"task": "secure_plugin", "device_ip": "192.168.1.20"})

    assert result["ok"] is True
    assert result["status"] == "success"
    assert captured == {
        "package_param": "com.demo.override",
        "device_ip_param": "10.0.0.8",
        "package_default": "com.demo.app",
        "device_ip_default": "192.168.1.20",
        "vars": {},
    }


def test_runner_plugin_explicit_package_param_overrides_manifest_default(tmp_path: Path, monkeypatch):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [
            {"name": "device_ip", "type": "string", "required": True},
            {"name": "package", "type": "string", "required": False, "default": "com.demo.default"},
        ],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        (
            "version: v1\n"
            "workflow: secure_plugin\n"
            "steps:\n"
            "  - kind: action\n"
            "    action: app.open\n"
            "    params:\n"
            "      package: com.demo.override\n"
            "  - kind: stop\n"
            "    status: success\n"
            "    message: ok\n"
        ),
    )
    runner = Runner()
    _attach_plugin_entry(runner, tmp_path, entry)

    packages: list[str] = []

    class _RecordingRpc:
        def init(self, ip: str, port: int, timeout: int) -> bool:
            return True

        def openApp(self, package: str) -> bool:
            packages.append(package)
            return True

        def close(self) -> None:
            return None

    monkeypatch.setattr("engine.actions.ui_actions.MytRpc", _RecordingRpc)

    result = runner.run({"task": "secure_plugin", "device_ip": "192.168.1.2"})

    assert result["ok"] is True
    assert result["status"] == "success"
    assert packages == ["com.demo.override"]


def test_runner_plugin_target_device_ip_reaches_action_when_payload_omits_runtime_plumbing(tmp_path: Path, monkeypatch):
    manifest_payload = {
        "api_version": "v1",
        "kind": "plugin",
        "name": "secure_plugin",
        "version": "1.0.0",
        "display_name": "Secure Plugin",
        "inputs": [
            {"name": "device_ip", "type": "string", "required": False},
            {"name": "package", "type": "string", "required": False, "default": "com.demo.app"},
        ],
    }
    entry = _make_plugin_entry(
        tmp_path,
        manifest_payload,
        (
            "version: v1\n"
            "workflow: secure_plugin\n"
            "steps:\n"
            "  - kind: action\n"
            "    action: app.open\n"
            "    params: {}\n"
            "  - kind: stop\n"
            "    status: success\n"
            "    message: ok\n"
        ),
    )
    runner = Runner()
    _attach_plugin_entry(runner, tmp_path, entry)

    calls: list[tuple[str, int, int]] = []
    packages: list[str] = []

    class _RecordingRpc:
        def init(self, ip: str, port: int, timeout: int) -> bool:
            calls.append((ip, port, timeout))
            return True

        def openApp(self, package: str) -> bool:
            packages.append(package)
            return True

        def close(self) -> None:
            return None

    monkeypatch.setattr("engine.actions.ui_actions.MytRpc", _RecordingRpc)

    result = runner.run(
        {
            "task": "secure_plugin",
        },
        runtime={"target": {"device_ip": "10.0.0.5", "rpa_port": 39002}},
    )

    assert result["ok"] is True
    assert result["status"] == "success"
    assert calls == [("10.0.0.5", 39002, 5)]
    assert packages == ["com.demo.app"]
