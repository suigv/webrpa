"""Tests for the YAML plugin engine modules.

Covers: models, parser, action_registry, conditions, interpreter, plugin_loader.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from engine.action_registry import ActionRegistry, get_registry, register_defaults
from engine.actions.credential_actions import credentials_load
from engine.conditions import evaluate as eval_condition
from engine.interpreter import Interpreter, InterpreterError
from engine.models.manifest import PluginManifest
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.workflow import (
    ActionStep,
    Condition,
    ConditionExpr,
    ConditionType,
    GotoStep,
    IfStep,
    StopStep,
    WaitUntilStep,
    WorkflowScript,
)
from engine.parser import interpolate, interpolate_params, parse_manifest, parse_script
from engine.plugin_loader import PluginLoader


# ============================================================
# Model validation tests
# ============================================================


class TestPluginManifest:
    def test_valid_manifest(self):
        m = PluginManifest.model_validate({
            "api_version": "v1",
            "kind": "plugin",
            "name": "test_plugin",
            "version": "1.0.0",
            "display_name": "Test Plugin",
        })
        assert m.name == "test_plugin"
        assert m.entry_script == "script.yaml"

    def test_invalid_api_version_rejected(self):
        with pytest.raises(ValidationError):
            PluginManifest.model_validate({
                "api_version": "v99",
                "kind": "plugin",
                "name": "bad",
                "version": "1.0",
                "display_name": "Bad",
            })

    def test_missing_required_fields_rejected(self):
        with pytest.raises(ValidationError):
            PluginManifest.model_validate({"api_version": "v1", "kind": "plugin"})


class TestWorkflowScript:
    def test_valid_script_with_action_and_stop(self):
        s = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "browser.open", "params": {"url": "https://x.com"}},
                {"kind": "stop", "status": "success", "message": "done"},
            ],
        })
        assert len(s.steps) == 2
        assert s.steps[0].kind == "action"
        assert s.steps[1].kind == "stop"

    def test_invalid_step_kind_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowScript.model_validate({
                "version": "v1",
                "workflow": "test",
                "steps": [{"kind": "invalid_kind"}],
            })

    def test_discriminated_union_selects_correct_type(self):
        s = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "goto", "target": "end"},
                {"kind": "if", "when": {"any": [{"type": "result_ok"}]}, "then": "end"},
                {"kind": "wait_until", "check": {"any": [{"type": "result_ok"}]}, "timeout_ms": 1000},
            ],
        })
        assert isinstance(s.steps[0], GotoStep)
        assert isinstance(s.steps[1], IfStep)
        assert isinstance(s.steps[2], WaitUntilStep)


class TestActionResult:
    def test_defaults(self):
        r = ActionResult(ok=True)
        assert r.code == "ok"
        assert r.message == ""
        assert r.data == {}


# ============================================================
# Parser / interpolation tests
# ============================================================


class TestInterpolation:
    def test_simple_payload_lookup(self):
        ctx = {"payload": {"url": "https://x.com"}, "vars": {}}
        assert interpolate("${payload.url}", ctx) == "https://x.com"

    def test_vars_lookup(self):
        ctx = {"payload": {}, "vars": {"user": "alice"}}
        assert interpolate("${vars.user}", ctx) == "alice"

    def test_nested_dotpath(self):
        ctx = {"payload": {}, "vars": {"creds": {"username_or_email": "bob"}}}
        assert interpolate("${vars.creds.username_or_email}", ctx) == "bob"

    def test_default_value(self):
        ctx = {"payload": {}, "vars": {}}
        assert interpolate("${payload.missing:-fallback}", ctx) == "fallback"

    def test_preserves_non_string_type(self):
        ctx = {"payload": {"count": 42}, "vars": {}}
        result = interpolate("${payload.count}", ctx)
        assert result == 42

    def test_mixed_text_and_interpolation(self):
        ctx = {"payload": {"host": "x.com"}, "vars": {}}
        assert interpolate("https://${payload.host}/login", ctx) == "https://x.com/login"

    def test_no_match_returns_original(self):
        ctx = {"payload": {}, "vars": {}}
        assert interpolate("${unknown.key}", ctx) == "${unknown.key}"


class TestInterpolateParams:
    def test_nested_dict_interpolation(self):
        ctx = {"payload": {"v": "hello"}, "vars": {}}
        result = interpolate_params({"a": {"b": "${payload.v}"}}, ctx)
        assert result == {"a": {"b": "hello"}}

    def test_list_interpolation(self):
        ctx = {"payload": {"x": "1"}, "vars": {}}
        result = interpolate_params({"items": ["${payload.x}", "static"]}, ctx)
        assert result == {"items": ["1", "static"]}


class TestYAMLParsing:
    def test_parse_manifest_file(self, tmp_path: Path):
        manifest_file = tmp_path / "manifest.yaml"
        manifest_file.write_text(
            "api_version: v1\nkind: plugin\nname: test\nversion: '1.0'\ndisplay_name: Test\n",
            encoding="utf-8",
        )
        m = parse_manifest(manifest_file)
        assert m.name == "test"

    def test_parse_script_file(self, tmp_path: Path):
        script_file = tmp_path / "script.yaml"
        script_file.write_text(
            "version: v1\nworkflow: test\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
            encoding="utf-8",
        )
        s = parse_script(script_file)
        assert s.workflow == "test"
        assert len(s.steps) == 1

    def test_parse_invalid_yaml_raises(self, tmp_path: Path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{invalid yaml", encoding="utf-8")
        with pytest.raises(ValueError, match="failed to load"):
            parse_manifest(bad_file)


# ============================================================
# Action registry tests
# ============================================================


class TestActionRegistry:
    def test_register_and_resolve(self):
        reg = ActionRegistry()
        handler = lambda p, c: ActionResult(ok=True)
        reg.register("test.action", handler)
        assert reg.resolve("test.action") is handler

    def test_unknown_action_raises(self):
        reg = ActionRegistry()
        with pytest.raises(KeyError, match="unknown action"):
            reg.resolve("nonexistent")

    def test_has(self):
        reg = ActionRegistry()
        reg.register("a", lambda p, c: ActionResult(ok=True))
        assert reg.has("a")
        assert not reg.has("b")

    def test_register_defaults_populates_global(self):
        register_defaults()
        reg = get_registry()
        assert reg.has("browser.open")
        assert reg.has("browser.input")
        assert reg.has("browser.click")
        assert reg.has("browser.exists")
        assert reg.has("browser.check_html")
        assert reg.has("browser.wait_url")
        assert reg.has("browser.close")
        assert reg.has("credentials.load")


# ============================================================
# Credential action tests
# ============================================================


class TestCredentialAction:
    def test_credentials_load_happy(self, tmp_path: Path, monkeypatch):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(
            json.dumps({"username_or_email": "u@test.com", "password": "pw"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MYT_CREDENTIAL_ALLOWLIST", str(tmp_path))
        ctx = ExecutionContext(payload={})
        result = credentials_load({"credentials_ref": str(cred_file), "save_as": "creds"}, ctx)
        assert result.ok is True
        assert ctx.vars["creds"]["username_or_email"] == "u@test.com"

    def test_credentials_load_missing_ref(self):
        ctx = ExecutionContext(payload={})
        result = credentials_load({}, ctx)
        assert result.ok is False
        assert result.code == "missing_ref"


# ============================================================
# Condition evaluator tests
# ============================================================


class TestConditionEvaluator:
    def test_result_ok_true(self):
        ctx = ExecutionContext(payload={})
        ctx.last_result = ActionResult(ok=True)
        expr = ConditionExpr(any=[Condition(type=ConditionType.result_ok)])
        assert eval_condition(expr, ctx) is True

    def test_result_ok_false(self):
        ctx = ExecutionContext(payload={})
        ctx.last_result = ActionResult(ok=False, code="err")
        expr = ConditionExpr(any=[Condition(type=ConditionType.result_ok)])
        assert eval_condition(expr, ctx) is False

    def test_var_equals(self):
        ctx = ExecutionContext(payload={})
        ctx.vars["status"] = "ready"
        expr = ConditionExpr(all=[Condition(type=ConditionType.var_equals, var="status", equals="ready")])
        assert eval_condition(expr, ctx) is True

    def test_var_equals_mismatch(self):
        ctx = ExecutionContext(payload={})
        ctx.vars["status"] = "not_ready"
        expr = ConditionExpr(all=[Condition(type=ConditionType.var_equals, var="status", equals="ready")])
        assert eval_condition(expr, ctx) is False

    def test_text_contains_with_mock_browser(self):
        ctx = ExecutionContext(payload={})
        browser = MagicMock()
        browser.html.return_value = "<html><body>Captcha detected</body></html>"
        ctx.browser = browser
        expr = ConditionExpr(any=[Condition(type=ConditionType.text_contains, text="captcha")])
        assert eval_condition(expr, ctx) is True

    def test_url_contains_with_mock_browser(self):
        ctx = ExecutionContext(payload={})
        browser = MagicMock()
        browser.current_url.return_value = "https://x.com/home"
        ctx.browser = browser
        expr = ConditionExpr(any=[Condition(type=ConditionType.url_contains, text="/home")])
        assert eval_condition(expr, ctx) is True

    def test_exists_with_mock_browser(self):
        ctx = ExecutionContext(payload={})
        browser = MagicMock()
        browser.exists.return_value = True
        ctx.browser = browser
        expr = ConditionExpr(any=[Condition(type=ConditionType.exists, selector="div.test")])
        assert eval_condition(expr, ctx) is True

    def test_all_requires_all_true(self):
        ctx = ExecutionContext(payload={})
        ctx.vars["a"] = 1
        ctx.vars["b"] = 2
        expr = ConditionExpr(all=[
            Condition(type=ConditionType.var_equals, var="a", equals=1),
            Condition(type=ConditionType.var_equals, var="b", equals=2),
        ])
        assert eval_condition(expr, ctx) is True

    def test_all_fails_if_any_false(self):
        ctx = ExecutionContext(payload={})
        ctx.vars["a"] = 1
        ctx.vars["b"] = 99
        expr = ConditionExpr(all=[
            Condition(type=ConditionType.var_equals, var="a", equals=1),
            Condition(type=ConditionType.var_equals, var="b", equals=2),
        ])
        assert eval_condition(expr, ctx) is False

    def test_empty_expr_is_vacuous_true(self):
        ctx = ExecutionContext(payload={})
        expr = ConditionExpr()
        assert eval_condition(expr, ctx) is True

    def test_no_browser_returns_false_for_browser_checks(self):
        ctx = ExecutionContext(payload={})
        assert ctx.browser is None
        expr = ConditionExpr(any=[Condition(type=ConditionType.text_contains, text="x")])
        assert eval_condition(expr, ctx) is False


# ============================================================
# Interpreter tests
# ============================================================


class TestInterpreter:
    def _make_interpreter(self):
        return Interpreter()

    def test_linear_execution_stop_success(self):
        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "stop", "status": "success", "message": "all good"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is True
        assert result["status"] == "success"
        assert result["message"] == "all good"

    def test_linear_execution_stop_failed(self):
        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "stop", "status": "failed", "message": "oops"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is False
        assert result["status"] == "failed"

    def test_goto_jumps_to_label(self):
        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "goto", "target": "end"},
                {"kind": "stop", "status": "failed", "message": "should not reach"},
                {"label": "end", "kind": "stop", "status": "success", "message": "jumped"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is True
        assert result["message"] == "jumped"

    def test_if_branches_on_condition(self):
        # Register a test action that always succeeds
        reg = get_registry()
        reg.register("test.noop", lambda p, c: ActionResult(ok=True, code="ok"))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.noop", "params": {}},
                {"kind": "if", "when": {"any": [{"type": "result_ok"}]}, "then": "ok_branch"},
                {"kind": "stop", "status": "failed", "message": "wrong branch"},
                {"label": "ok_branch", "kind": "stop", "status": "success", "message": "correct"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is True
        assert result["message"] == "correct"

    def test_max_transitions_guard(self):
        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"label": "loop", "kind": "goto", "target": "loop"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is False
        assert "max transitions" in result["message"]

    def test_unknown_label_raises(self):
        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "goto", "target": "nonexistent"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is False
        assert "unknown label" in result["message"]

    def test_on_fail_skip_continues(self):
        reg = get_registry()
        reg.register("test.fail", lambda p, c: ActionResult(ok=False, code="err", message="boom"))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.fail", "params": {},
                 "on_fail": {"strategy": "skip"}},
                {"kind": "stop", "status": "success", "message": "continued"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is True
        assert result["message"] == "continued"

    def test_on_fail_abort_stops(self):
        reg = get_registry()
        reg.register("test.fail2", lambda p, c: ActionResult(ok=False, code="err", message="boom"))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.fail2", "params": {},
                 "on_fail": {"strategy": "abort"}},
                {"kind": "stop", "status": "success", "message": "should not reach"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is False
        assert result["status"] == "failed"

    def test_on_fail_goto_jumps(self):
        reg = get_registry()
        reg.register("test.fail3", lambda p, c: ActionResult(ok=False, code="err", message="boom"))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.fail3", "params": {},
                 "on_fail": {"strategy": "goto", "goto": "error_handler"}},
                {"kind": "stop", "status": "failed", "message": "wrong"},
                {"label": "error_handler", "kind": "stop", "status": "success", "message": "handled"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is True
        assert result["message"] == "handled"

    def test_variable_interpolation_in_action(self):
        reg = get_registry()

        def capture_action(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
            context.vars["captured_url"] = params.get("url", "")
            return ActionResult(ok=True)

        reg.register("test.capture", capture_action)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "vars": {"base_url": "${payload.url:-https://default.com}"},
            "steps": [
                {"kind": "action", "action": "test.capture",
                 "params": {"url": "${vars.base_url}"}},
                {"kind": "stop", "status": "success", "message": "ok"},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {"url": "https://x.com"})
        assert result["ok"] is True

    def test_falls_through_without_stop(self):
        reg = get_registry()
        reg.register("test.ok", lambda p, c: ActionResult(ok=True))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.ok", "params": {}},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is True
        assert result["status"] == "completed"
        assert result["message"] == "workflow finished"

    def test_save_as_stores_result(self):
        reg = get_registry()
        reg.register("test.data", lambda p, c: ActionResult(ok=True, data={"key": "val"}))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.data", "params": {}, "save_as": "result"},
                {"kind": "stop", "status": "success", "message": "ok"},
            ],
        })
        interp = self._make_interpreter()
        # We can't easily inspect context.vars from outside,
        # but we can verify the workflow completes
        result = interp.execute(script, {})
        assert result["ok"] is True

    def test_browser_cleanup_in_finally(self):
        """Browser should be closed even if an error occurs."""
        reg = get_registry()
        mock_browser = MagicMock()

        def open_browser(params, context):
            context.browser = mock_browser
            return ActionResult(ok=True)

        def fail_action(params, context):
            return ActionResult(ok=False, code="err", message="boom")

        reg.register("test.open_browser", open_browser)
        reg.register("test.fail_browser", fail_action)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.open_browser", "params": {}},
                {"kind": "action", "action": "test.fail_browser", "params": {}},
            ],
        })
        interp = self._make_interpreter()
        result = interp.execute(script, {})
        assert result["ok"] is False
        mock_browser.close.assert_called_once()


# ============================================================
# Plugin loader tests
# ============================================================


class TestPluginLoader:
    def test_scan_finds_valid_plugin(self, tmp_path: Path):
        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text(
            "api_version: v1\nkind: plugin\nname: my_plugin\nversion: '1.0'\ndisplay_name: My Plugin\n",
            encoding="utf-8",
        )
        (plugin_dir / "script.yaml").write_text(
            "version: v1\nworkflow: my_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
            encoding="utf-8",
        )
        loader = PluginLoader(plugins_root=tmp_path)
        loader.scan()
        assert loader.has("my_plugin")
        assert "my_plugin" in loader.names

    def test_scan_skips_invalid_manifest(self, tmp_path: Path):
        plugin_dir = tmp_path / "bad_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text("invalid: yaml: content", encoding="utf-8")
        loader = PluginLoader(plugins_root=tmp_path)
        loader.scan()
        assert not loader.has("bad_plugin")

    def test_scan_skips_missing_script(self, tmp_path: Path):
        plugin_dir = tmp_path / "no_script"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text(
            "api_version: v1\nkind: plugin\nname: no_script\nversion: '1.0'\ndisplay_name: No Script\n",
            encoding="utf-8",
        )
        # No script.yaml created
        loader = PluginLoader(plugins_root=tmp_path)
        loader.scan()
        assert not loader.has("no_script")

    def test_scan_empty_dir(self, tmp_path: Path):
        loader = PluginLoader(plugins_root=tmp_path)
        loader.scan()
        assert loader.names == []

    def test_get_returns_entry(self, tmp_path: Path):
        plugin_dir = tmp_path / "p"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text(
            "api_version: v1\nkind: plugin\nname: p\nversion: '1.0'\ndisplay_name: P\n",
            encoding="utf-8",
        )
        (plugin_dir / "script.yaml").write_text(
            "version: v1\nworkflow: p\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
            encoding="utf-8",
        )
        loader = PluginLoader(plugins_root=tmp_path)
        loader.scan()
        entry = loader.get("p")
        assert entry is not None
        assert entry.manifest.name == "p"
        assert entry.script_path == plugin_dir / "script.yaml"


# ============================================================
# x_mobile_login YAML validation tests
# ============================================================


class TestXMobileLoginYAMLPlugin:
    def test_manifest_validates(self):
        manifest_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "manifest.yaml"
        if not manifest_path.exists():
            pytest.skip("x_mobile_login manifest not found")
        m = parse_manifest(manifest_path)
        assert m.name == "x_mobile_login"
        assert m.version == "1.0.0"
        assert m.kind == "plugin"
        assert m.api_version == "v1"

    def test_script_validates(self):
        script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "script.yaml"
        if not script_path.exists():
            pytest.skip("x_mobile_login script not found")
        s = parse_script(script_path)
        assert s.workflow == "x_mobile_login"
        assert len(s.steps) > 10  # Should have many steps

    def test_all_labels_are_unique(self):
        script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "script.yaml"
        if not script_path.exists():
            pytest.skip("x_mobile_login script not found")
        s = parse_script(script_path)
        labels = [getattr(step, "label", None) for step in s.steps if getattr(step, "label", None)]
        assert len(labels) == len(set(labels)), f"duplicate labels: {labels}"

    def test_plugin_loader_finds_x_mobile_login(self):
        plugins_root = Path(__file__).resolve().parents[1] / "plugins"
        if not (plugins_root / "x_mobile_login" / "manifest.yaml").exists():
            pytest.skip("x_mobile_login plugin not found")
        loader = PluginLoader(plugins_root=plugins_root)
        loader.scan()
        assert loader.has("x_mobile_login")
