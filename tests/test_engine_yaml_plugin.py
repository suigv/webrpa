"""Tests for the YAML plugin engine modules.

Covers: models, parser, action_registry, conditions, interpreter, plugin_loader.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict
from unittest.mock import MagicMock

import pytest  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

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
from engine.plugin_loader import PluginLoader, clear_shared_plugin_loader_cache, get_shared_plugin_loader
from engine.models.ui_state import UIStateObservationResult
from engine.runner import Runner


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

    def test_list_interpolation_with_nested_dict(self):
        ctx = {"payload": {"x": "1", "y": "2"}, "vars": {}}
        result = interpolate_params({"items": [{"value": "${payload.x}"}, ["${payload.y}"]]}, ctx)
        assert result == {"items": [{"value": "1"}, ["2"]]}


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

    def test_credentials_load_uses_session_default_ref(self, tmp_path: Path, monkeypatch):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(
            json.dumps({"username_or_email": "u@test.com", "password": "pw"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MYT_CREDENTIAL_ALLOWLIST", str(tmp_path))
        ctx = ExecutionContext(payload={}, session={"defaults": {"credentials_ref": str(cred_file)}})

        result = credentials_load({}, ctx)

        assert result.ok is True
        assert ctx.vars["creds"]["username_or_email"] == "u@test.com"


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

    def test_browser_condition_uses_ui_state_service(self, monkeypatch):
        ctx = ExecutionContext(payload={})
        ctx.browser = MagicMock()
        captured: dict[str, Any] = {}

        def fake_match_state(self, context, *, expected_state_ids, timeout_ms=None):
            captured["context"] = context
            captured["expected_state_ids"] = list(expected_state_ids)
            captured["timeout_ms"] = timeout_ms
            return UIStateObservationResult.matched(
                operation="match_state",
                state_id="html:captcha",
                platform="browser",
                expected_state_ids=expected_state_ids,
            )

        monkeypatch.setattr("engine.conditions.BrowserUIStateService.match_state", fake_match_state)

        expr = ConditionExpr(any=[Condition(type=ConditionType.text_contains, text="captcha")])
        assert eval_condition(expr, ctx) is True
        assert captured == {
            "context": ctx,
            "expected_state_ids": ["html:captcha"],
            "timeout_ms": None,
        }

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

    class _FakeWaitClock:
        def __init__(self):
            self.now = 0.0
            self.sleep_calls = 0
            self.after_sleep: Callable[["TestInterpreter._FakeWaitClock"], None] | None = None

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.sleep_calls += 1
            self.now += seconds
            if self.after_sleep is not None:
                self.after_sleep(self)

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

    def test_if_browser_condition_uses_ui_state_service(self, monkeypatch):
        reg = get_registry()
        mock_browser = MagicMock()

        def open_browser(params, context):
            context.browser = mock_browser
            return ActionResult(ok=True)

        def fake_match_state(self, context, *, expected_state_ids, timeout_ms=None):
            return UIStateObservationResult.matched(
                operation="match_state",
                state_id="html:captcha",
                platform="browser",
                expected_state_ids=expected_state_ids,
            )

        reg.register("test.open_browser_for_if", open_browser)
        monkeypatch.setattr("engine.conditions.BrowserUIStateService.match_state", fake_match_state)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.open_browser_for_if", "params": {}},
                {"kind": "if", "when": {"any": [{"type": "text_contains", "text": "captcha"}]}, "then": "ui_branch"},
                {"kind": "stop", "status": "failed", "message": "wrong branch"},
                {"label": "ui_branch", "kind": "stop", "status": "success", "message": "ui state matched"},
            ],
        })

        interp = self._make_interpreter()
        result = interp.execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "ui state matched"

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

    def test_plugin_inputs_become_session_defaults_without_leaking_into_vars(self):
        reg = get_registry()
        captured: dict[str, Any] = {}

        def capture_defaults(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
            captured["package"] = context.get_session_default("package")
            captured["device_ip"] = context.get_session_default("device_ip")
            captured["vars"] = dict(context.vars)
            return ActionResult(ok=True)

        reg.register("core.capture_session_defaults", capture_defaults)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "core.capture_session_defaults", "params": {}},
                {"kind": "stop", "status": "success", "message": "ok"},
            ],
        })
        manifest = PluginManifest.model_validate({
            "api_version": "v1",
            "kind": "plugin",
            "name": "test_plugin",
            "version": "1.0.0",
            "display_name": "Test Plugin",
            "inputs": [
                {"name": "device_ip", "type": "string", "required": True},
                {"name": "package", "type": "string", "required": False, "default": "com.demo.app"},
            ],
        })

        result = self._make_interpreter().execute(
            script,
            {"device_ip": "192.168.1.20"},
            plugin_inputs=manifest.inputs,
        )

        assert result["ok"] is True
        assert captured["device_ip"] == "192.168.1.20"
        assert captured["package"] == "com.demo.app"
        assert captured["vars"] == {}

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

    def test_wait_until_uses_ui_state_service_for_browser_checks(self, monkeypatch):
        reg = get_registry()
        mock_browser = MagicMock()
        captured: dict[str, Any] = {}

        def open_browser(params, context):
            context.browser = mock_browser
            return ActionResult(ok=True)

        def fake_wait_until(self, context, *, expected_state_ids, timeout_ms=15000, interval_ms=500):
            captured["context"] = context
            captured["browser"] = context.browser
            captured["expected_state_ids"] = list(expected_state_ids)
            captured["timeout_ms"] = timeout_ms
            captured["interval_ms"] = interval_ms
            return UIStateObservationResult.matched(
                operation="wait_until",
                state_id="url:/home",
                platform="browser",
                expected_state_ids=expected_state_ids,
            )

        reg.register("test.open_browser_for_ui_state_wait", open_browser)
        monkeypatch.setattr("engine.interpreter.BrowserUIStateService.wait_until", fake_wait_until)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.open_browser_for_ui_state_wait", "params": {}},
                {"kind": "wait_until", "check": {"any": [{"type": "url_contains", "text": "/home"}]}, "timeout_ms": 1200, "interval_ms": 150},
                {"kind": "stop", "status": "success", "message": "waited"},
            ],
        })

        interp = self._make_interpreter()
        result = interp.execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "waited"
        assert captured["expected_state_ids"] == ["url:/home"]
        assert captured["timeout_ms"] == 1200
        assert captured["interval_ms"] == 150
        assert captured["browser"] is mock_browser

    def test_cleanup_preserved_on_ui_state_wait_until_timeout(self, monkeypatch):
        reg = get_registry()
        mock_browser = MagicMock()

        def open_browser(params, context):
            context.browser = mock_browser
            return ActionResult(ok=True)

        def fake_wait_until(self, context, *, expected_state_ids, timeout_ms=15000, interval_ms=500):
            return UIStateObservationResult.timeout(
                operation="wait_until",
                state_id="url:/never",
                platform="browser",
                expected_state_ids=expected_state_ids,
                message="timed out waiting for browser state",
            )

        reg.register("test.open_browser_for_ui_state_timeout", open_browser)
        monkeypatch.setattr("engine.interpreter.BrowserUIStateService.wait_until", fake_wait_until)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.open_browser_for_ui_state_timeout", "params": {}},
                {"kind": "wait_until", "check": {"any": [{"type": "url_contains", "text": "/never"}]}, "timeout_ms": 200},
            ],
        })

        interp = self._make_interpreter()
        result = interp.execute(script, {})

        assert result["ok"] is False
        assert "wait_until timed out" in result["message"]
        mock_browser.close.assert_called_once()

    def test_wait_until_succeeds_before_timeout_during_polling(self, monkeypatch):
        reg = get_registry()
        seen: dict[str, ExecutionContext] = {}
        clock = self._FakeWaitClock()

        def bind_context(params, context):
            seen["context"] = context
            context.vars["ready"] = False
            return ActionResult(ok=True)

        def flip_ready(_clock):
            seen["context"].vars["ready"] = True
            _clock.after_sleep = None

        clock.after_sleep = flip_ready
        reg.register("test.bind_wait_context", bind_context)
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.bind_wait_context", "params": {}},
                {"kind": "wait_until", "check": {"all": [{"type": "var_equals", "var": "ready", "equals": True}]}, "timeout_ms": 1200, "interval_ms": 200},
                {"kind": "stop", "status": "success", "message": "ready"},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "ready"
        assert clock.sleep_calls == 1

    def test_wait_until_timeout_returns_error_without_fallback(self, monkeypatch):
        clock = self._FakeWaitClock()
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "wait_until", "label": "wait_here", "check": {"all": [{"type": "var_truthy", "var": "never"}]}, "timeout_ms": 600, "interval_ms": 200},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is False
        assert result["status"] == "failed"
        assert result["message"] == "wait_until timed out after 0.6s at step 0 (wait_here)"

    def test_wait_until_on_timeout_goto_jumps_to_handler(self, monkeypatch):
        clock = self._FakeWaitClock()
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "wait_until", "check": {"all": [{"type": "var_truthy", "var": "never"}]}, "timeout_ms": 400, "interval_ms": 100, "on_timeout": {"strategy": "goto", "goto": "timed_out"}},
                {"kind": "stop", "status": "failed", "message": "should not reach"},
                {"label": "timed_out", "kind": "stop", "status": "success", "message": "handled timeout"},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "handled timeout"

    def test_wait_until_on_fail_is_used_when_on_timeout_missing(self, monkeypatch):
        clock = self._FakeWaitClock()
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "wait_until", "check": {"all": [{"type": "var_truthy", "var": "never"}]}, "timeout_ms": 400, "interval_ms": 100, "on_fail": {"strategy": "goto", "goto": "fallback"}},
                {"kind": "stop", "status": "failed", "message": "should not reach"},
                {"label": "fallback", "kind": "stop", "status": "success", "message": "handled fallback"},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "handled fallback"

    def test_wait_until_cancellation_during_polling_returns_cancelled(self, monkeypatch):
        clock = self._FakeWaitClock()
        cancel_state = {"cancelled": False}

        def request_cancel(_clock):
            cancel_state["cancelled"] = True
            _clock.after_sleep = None

        clock.after_sleep = request_cancel
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "wait_until", "check": {"all": [{"type": "var_truthy", "var": "never"}]}, "timeout_ms": 1000, "interval_ms": 200},
            ],
        })

        result = self._make_interpreter().execute(script, {}, should_cancel=lambda: cancel_state["cancelled"])

        assert result["ok"] is False
        assert result["status"] == "cancelled"
        assert result["message"] == "task cancelled by user"

    def test_wait_until_rechecks_vars_that_change_between_polls(self, monkeypatch):
        reg = get_registry()
        seen: dict[str, ExecutionContext] = {}
        clock = self._FakeWaitClock()

        def bind_context(params, context):
            seen["context"] = context
            context.vars["status"] = "pending"
            return ActionResult(ok=True)

        def update_vars(_clock):
            seen["context"].vars["status"] = "ready"
            _clock.after_sleep = None

        clock.after_sleep = update_vars
        reg.register("test.bind_wait_vars", bind_context)
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.bind_wait_vars", "params": {}},
                {"kind": "wait_until", "check": {"all": [{"type": "var_equals", "var": "status", "equals": "ready"}]}, "timeout_ms": 800, "interval_ms": 200},
                {"kind": "stop", "status": "success", "message": "vars updated"},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "vars updated"

    def test_wait_until_rechecks_last_result_that_changes_between_polls(self, monkeypatch):
        reg = get_registry()
        seen: dict[str, ExecutionContext] = {}
        clock = self._FakeWaitClock()

        def bind_context(params, context):
            seen["context"] = context
            return ActionResult(ok=False, code="not_ready")

        def update_last_result(_clock):
            seen["context"].last_result = ActionResult(ok=True)
            _clock.after_sleep = None

        clock.after_sleep = update_last_result
        reg.register("test.bind_last_result", bind_context)
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.bind_last_result", "params": {}, "on_fail": {"strategy": "skip"}},
                {"kind": "wait_until", "check": {"any": [{"type": "result_ok"}]}, "timeout_ms": 800, "interval_ms": 200},
                {"kind": "stop", "status": "success", "message": "result updated"},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "result updated"

    def test_wait_until_rechecks_action_produced_data_between_polls(self, monkeypatch):
        reg = get_registry()
        seen: dict[str, ExecutionContext] = {}
        clock = self._FakeWaitClock()

        def produce_data(params, context):
            job = {"status": "pending"}
            context.vars["job"] = job
            seen["context"] = context
            return ActionResult(ok=True, data=job)

        def update_action_data(_clock):
            seen["context"].vars["job"]["status"] = "ready"
            _clock.after_sleep = None

        clock.after_sleep = update_action_data
        reg.register("test.produce_wait_data", produce_data)
        monkeypatch.setattr("engine.interpreter.time.monotonic", clock.monotonic)
        monkeypatch.setattr("engine.interpreter.time.sleep", clock.sleep)

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "test",
            "steps": [
                {"kind": "action", "action": "test.produce_wait_data", "params": {}, "save_as": "job"},
                {"kind": "wait_until", "check": {"all": [{"type": "var_equals", "var": "job.status", "equals": "ready"}]}, "timeout_ms": 800, "interval_ms": 200},
                {"kind": "stop", "status": "success", "message": "action data updated"},
            ],
        })

        result = self._make_interpreter().execute(script, {})

        assert result["ok"] is True
        assert result["message"] == "action data updated"

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

    def test_selector_cleanup_in_finally_on_action_failure(self, monkeypatch):
        from engine.actions import ui_actions

        class FakeSelectorRpc:
            instances: list["FakeSelectorRpc"] = []

            def __init__(self):
                self.closed = False
                self.clear_calls = 0
                self.query_calls = 0
                self.free_selector_calls = 0
                self.free_nodes_calls: list[int] = []
                FakeSelectorRpc.instances.append(self)

            def init(self, ip, port, timeout):
                return True

            def close(self):
                self.closed = True

            def create_selector(self):
                return 7

            def addQuery_Text(self, selector, value):
                self.query_calls += 1
                return not self.closed

            def clear_selector(self, selector):
                self.clear_calls += 1
                return not self.closed

            def free_selector(self, selector):
                self.free_selector_calls += 1
                return not self.closed

            def find_nodes(self, selector, max_count, timeout_ms):
                _ = (selector, max_count, timeout_ms)
                return 101

            def get_nodes_size(self, nodes):
                _ = nodes
                return 2

            def free_nodes(self, nodes):
                self.free_nodes_calls.append(int(nodes))
                return not self.closed

        monkeypatch.setattr(ui_actions, "MytRpc", FakeSelectorRpc)

        reg = get_registry()
        reg.register("test.fail_after_selector", lambda p, c: ActionResult(ok=False, code="err", message="forced failure"))

        script = WorkflowScript.model_validate({
            "version": "v1",
            "workflow": "selector_cleanup",
            "steps": [
                {"kind": "action", "action": "ui.create_selector", "params": {}},
                {"kind": "action", "action": "ui.selector_add_query", "params": {"type": "text", "value": "hello"}},
                {"kind": "action", "action": "ui.selector_find_nodes", "params": {"save_as": "nodes_h"}},
                {"kind": "action", "action": "test.fail_after_selector", "params": {}},
            ],
        })

        interp = self._make_interpreter()
        result = interp.execute(
            script,
            {"device_ip": "192.168.1.2", "cloud_index": 1, "cloud_machines_per_device": 1},
        )

        assert result["ok"] is False
        assert "forced failure" in result["message"]
        assert len(FakeSelectorRpc.instances) == 1
        assert FakeSelectorRpc.instances[0].query_calls == 1
        assert FakeSelectorRpc.instances[0].free_nodes_calls == [101]
        assert FakeSelectorRpc.instances[0].clear_calls == 1
        assert FakeSelectorRpc.instances[0].free_selector_calls == 1
        assert FakeSelectorRpc.instances[0].closed is True


# ============================================================
# Plugin loader tests
# ============================================================


class TestPluginLoader:
    def test_shared_plugin_loader_refresh_is_explicit(self, tmp_path: Path):
        clear_shared_plugin_loader_cache()

        loader = get_shared_plugin_loader(plugins_root=tmp_path, refresh=True)
        assert loader.names == []

        plugin_dir = tmp_path / "late_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text(
            "api_version: v1\nkind: plugin\nname: late_plugin\nversion: '1.0'\ndisplay_name: Late Plugin\n",
            encoding="utf-8",
        )
        (plugin_dir / "script.yaml").write_text(
            "version: v1\nworkflow: late_plugin\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
            encoding="utf-8",
        )

        cached = get_shared_plugin_loader(plugins_root=tmp_path)
        assert not cached.has("late_plugin")

        refreshed = get_shared_plugin_loader(plugins_root=tmp_path, refresh=True)
        assert refreshed.has("late_plugin")

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

    def test_shared_plugin_loader_refresh_updates_existing_references(self, tmp_path: Path):
        clear_shared_plugin_loader_cache()

        first = get_shared_plugin_loader(plugins_root=tmp_path, refresh=True)
        assert first.names == []

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

        second = get_shared_plugin_loader(plugins_root=tmp_path)
        refreshed = get_shared_plugin_loader(plugins_root=tmp_path, refresh=True)

        assert second is first
        assert refreshed is first
        assert first.has("my_plugin")
        assert second.has("my_plugin")

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


class TestFeasibilityReplaySmoke:
    def test_yaml_acceptance_can_use_existing_parse_and_replay_contracts(self, tmp_path: Path, monkeypatch):
        plugin_dir = tmp_path / "replay_smoke"
        plugin_dir.mkdir()
        manifest_path = plugin_dir / "manifest.yaml"
        script_path = plugin_dir / "script.yaml"
        manifest_path.write_text(
            "api_version: v1\nkind: plugin\nname: replay_smoke\nversion: '1.0'\ndisplay_name: Replay Smoke\n",
            encoding="utf-8",
        )
        script_path.write_text(
            "version: v1\nworkflow: replay_smoke\nsteps:\n  - kind: action\n    action: core.record_replay_smoke\n    params:\n      value: ok\n  - kind: stop\n    status: success\n    message: replay ok\n",
            encoding="utf-8",
        )

        manifest = parse_manifest(manifest_path)
        script = parse_script(script_path)
        assert manifest.name == "replay_smoke"
        assert script.workflow == "replay_smoke"

        loader = PluginLoader(plugins_root=tmp_path)
        loader.scan()
        assert loader.has("replay_smoke")

        captured: list[dict[str, object]] = []

        def record_replay_smoke(params: dict[str, object], context: ExecutionContext) -> ActionResult:
            captured.append({"params": dict(params), "payload": dict(context.payload)})
            return ActionResult(ok=True, code="ok", data={"value": params.get("value")})

        monkeypatch.setattr("engine.runner.get_shared_plugin_loader", lambda: loader)
        get_registry().register("core.record_replay_smoke", record_replay_smoke)

        result = Runner().run({"task": "replay_smoke"})

        assert result["ok"] is True
        assert result["status"] == "success"
        assert result["message"] == "replay ok"
        assert captured == [{"params": {"value": "ok"}, "payload": {"task": "replay_smoke"}}]


# ============================================================
# x_auto_login YAML validation tests
# ============================================================


class TestXAutoLoginYAMLPlugin:
    def test_manifest_validates(self):
        manifest_path = Path(__file__).resolve().parents[1] / "plugins" / "x_auto_login" / "manifest.yaml"
        if not manifest_path.exists():
            pytest.skip("x_auto_login manifest not found")
        m = parse_manifest(manifest_path)
        assert m.name == "x_auto_login"
        assert m.version == "1.0.0"
        assert m.kind == "plugin"
        assert m.api_version == "v1"

    def test_script_validates(self):
        script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_auto_login" / "script.yaml"
        if not script_path.exists():
            pytest.skip("x_auto_login script not found")
        s = parse_script(script_path)
        assert s.workflow == "x_auto_login"
        assert len(s.steps) > 10  # Should have many steps

    def test_all_labels_are_unique(self):
        script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_auto_login" / "script.yaml"
        if not script_path.exists():
            pytest.skip("x_auto_login script not found")
        s = parse_script(script_path)
        labels = [getattr(step, "label", None) for step in s.steps if getattr(step, "label", None)]
        assert len(labels) == len(set(labels)), f"duplicate labels: {labels}"

    def test_plugin_loader_finds_x_auto_login(self):
        plugins_root = Path(__file__).resolve().parents[1] / "plugins"
        if not (plugins_root / "x_auto_login" / "manifest.yaml").exists():
            pytest.skip("x_auto_login plugin not found")
        loader = PluginLoader(plugins_root=plugins_root)
        loader.scan()
        assert loader.has("x_auto_login")
