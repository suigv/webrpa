from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from engine.action_dispatcher import dispatch_action
from engine.action_registry import get_registry, register_defaults
from engine.conditions import browser_condition_state_id
from engine.conditions import evaluate as eval_condition
from engine.models.manifest import PluginInput
from engine.models.runtime import ActionResult, ExecutionCancelled, ExecutionContext
from engine.models.workflow import (
    ActionStep,
    Condition,
    ConditionExpr,
    FailStrategy,
    GotoStep,
    IfStep,
    OnFail,
    Step,
    StopStep,
    WaitUntilStep,
    WorkflowScript,
)
from engine.parser import interpolate_params
from engine.ui_state_browser_service import BrowserUIStateService

logger = logging.getLogger(__name__)

MAX_TRANSITIONS = 500
WAIT_UNTIL_HARD_LIMIT_S = 120
WAIT_UNTIL_POLL_MAX_S = 0.2
WAIT_UNTIL_CANCEL_CHECK_S = 0.2


class InterpreterError(Exception):
    """Raised when the interpreter encounters an unrecoverable error."""


class Interpreter:
    """PC-based workflow interpreter.

    Executes a WorkflowScript by maintaining a program counter (pc)
    that steps through the list of steps. Supports labels, goto jumps,
    if branching, wait_until polling, and stop.
    """

    def __init__(self) -> None:
        register_defaults()

    def execute(
        self,
        script: WorkflowScript,
        payload: dict[str, Any],
        plugin_inputs: list[PluginInput] | None = None,
        should_cancel: Any = None,
        runtime: dict[str, Any] | None = None,
        emit_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Execute a workflow script with the given payload.

        Returns a result dict with ok, status, message, and workflow metadata.
        """
        context = ExecutionContext(
            payload=payload,
            session={
                "defaults": self._build_session_defaults(payload, plugin_inputs or [], runtime)
            },
            runtime=runtime,
        )
        context.should_cancel = should_cancel
        context.emit_event = emit_event
        # Merge script-level vars (with interpolation from payload)
        if script.vars:
            interp_ctx = {"payload": payload, "vars": context.vars}
            context.vars.update(interpolate_params(script.vars, interp_ctx))

        label_map = self._build_label_map(script.steps)
        registry = get_registry()

        try:
            while context.pc < len(script.steps):
                self._check_cancelled(context)
                step = script.steps[context.pc]
                context.jumped = False
                if isinstance(step, ActionStep):
                    self._exec_action(step, context, registry, label_map)
                elif isinstance(step, IfStep):
                    self._exec_if(step, context, label_map)
                elif isinstance(step, WaitUntilStep):
                    self._exec_wait_until(step, context, label_map)
                elif isinstance(step, GotoStep):
                    self._exec_goto(step, context, label_map)
                elif isinstance(step, StopStep):
                    return self._exec_stop(step, script.workflow)

                # Only auto-advance if no jump occurred
                if not context.jumped:
                    context.pc += 1
            # Fell through all steps without explicit stop
            res = {
                "ok": True,
                "workflow": script.workflow,
                "status": "completed",
                "message": "workflow finished",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if context.last_result:
                res["data"] = context.last_result.data
                res["code"] = context.last_result.code
            return res

        except InterpreterError as exc:
            return {
                "ok": False,
                "workflow": script.workflow,
                "status": "failed",
                "message": str(exc),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except ExecutionCancelled as exc:
            return {
                "ok": False,
                "workflow": script.workflow,
                "status": "cancelled",
                "message": str(exc),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:
            logger.exception("interpreter unexpected error")
            return {
                "ok": False,
                "workflow": script.workflow,
                "status": "error",
                "message": str(exc),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        finally:
            with suppress(Exception):
                context.close()
            try:
                from engine.actions import _ui_selector_support

                def _close_rpc(rpc: Any) -> None:
                    if rpc is None:
                        return
                    closer = getattr(rpc, "close", None)
                    if callable(closer):
                        closer()

                _ = _ui_selector_support.release_selector_context(context, close_rpc=_close_rpc)
            except Exception:
                logger.debug("failed to release selector context", exc_info=True)
            if context.browser is not None:
                with suppress(Exception):
                    context.browser.close()
                context.browser = None

    # ---- Step executors ----

    def _exec_action(
        self,
        step: ActionStep,
        context: ExecutionContext,
        registry: Any,
        label_map: dict[str, int],
    ) -> None:
        interp_ctx = {"payload": context.payload, "vars": context.vars}
        params = interpolate_params(step.params, interp_ctx)

        result = self._run_with_on_fail(
            lambda: dispatch_action(step.action, params, context, registry=registry),
            step.on_fail,
            context,
            label_map,
        )
        context.last_result = result

        # 实时推送动作执行结果
        if context.emit_event:
            # `label` is a human-readable hint from YAML (e.g. "go_home").
            display_label = str(step.label or step.action)
            context.emit_event(
                "task.action_result",
                {
                    "step": context.pc + 1,
                    "label": display_label,
                    "ok": result.ok,
                    "message": result.message,
                },
            )

        if step.save_as:
            context.vars[step.save_as] = (
                result.data
                if result.data
                else {
                    "ok": result.ok,
                    "code": result.code,
                    "message": result.message,
                }
            )

    def _exec_if(
        self,
        step: IfStep,
        context: ExecutionContext,
        label_map: dict[str, int],
    ) -> None:
        matched = eval_condition(step.when, context)
        target = step.then if matched else step.otherwise
        if target is not None:
            self._jump_to(target, context, label_map)

    def _exec_wait_until(
        self,
        step: WaitUntilStep,
        context: ExecutionContext,
        label_map: dict[str, int],
    ) -> None:
        timeout_ms = min(int(step.timeout_ms), int(WAIT_UNTIL_HARD_LIMIT_S * 1000))
        timeout_s = timeout_ms / 1000.0
        interval_s = step.interval_ms / 1000.0
        service_state_ids = self._browser_wait_state_ids(step.check, context)

        deadline = time.monotonic() + timeout_s
        first_iteration = True

        if service_state_ids:
            # 如果可以使用 Service 优化（如浏览器 URL 监听），我们依然尝试，但缩短单次等待时间以响应取消
            while time.monotonic() < deadline:
                self._check_cancelled(context)

                if first_iteration:
                    remaining_ms = timeout_ms
                    first_iteration = False
                else:
                    remaining_ms = int(max(0.0, (deadline - time.monotonic()) * 1000))
                if remaining_ms <= 0:
                    break

                # 每次最多让 Service 等待 2s，以便 Interpreter 及时收回控制权检查取消信号
                chunk_timeout_ms = int(min(float(remaining_ms), 2000.0))

                try:
                    result = BrowserUIStateService().wait_until(
                        context,
                        expected_state_ids=service_state_ids,
                        timeout_ms=chunk_timeout_ms,
                        interval_ms=step.interval_ms,
                    )
                    if result.ok:
                        return
                    # 如果不是超时（比如报错了），我们回退到普通轮询
                    if result.code != "timeout":
                        logger.debug(f"Service wait failed: {result.message}")
                except Exception:
                    logger.debug(
                        "service-backed wait_until failed; falling back to polling", exc_info=True
                    )

                # 普通轮询回退（事件驱动等待）
                if eval_condition(step.check, context):
                    return

                self._wait_interval_with_signal(context, min(interval_s, 1.0))
        else:
            # 纯条件轮询：用事件唤醒 + 背景轮询线程
            if self._wait_until_with_signal(step, context, deadline, interval_s):
                return

        # Timed out
        on_fail = step.on_timeout or step.on_fail
        if on_fail:
            self._handle_on_fail(on_fail, context, label_map, "wait_until timed out")
        else:
            raise InterpreterError(
                f"wait_until timed out after {timeout_s:.1f}s at step "
                f"{context.pc} ({step.label or 'unlabeled'})"
            )

    def _wait_interval_with_signal(self, context: ExecutionContext, timeout_s: float) -> None:
        if timeout_s <= 0:
            return
        wait_signal = context.wait_signal
        signaled = wait_signal.wait(timeout_s)
        if signaled:
            wait_signal.reset()

    def _wait_until_with_signal(
        self,
        step: WaitUntilStep,
        context: ExecutionContext,
        deadline: float,
        interval_s: float,
    ) -> bool:
        if eval_condition(step.check, context):
            return True

        wait_signal = context.wait_signal
        wait_signal.reset()
        stop_event = threading.Event()
        matched = {"ok": False}
        poll_interval = min(max(interval_s, 0.01), WAIT_UNTIL_POLL_MAX_S)

        def _poll() -> None:
            try:
                while not stop_event.is_set():
                    try:
                        context.check_cancelled()
                    except ExecutionCancelled:
                        return
                    if eval_condition(step.check, context):
                        matched["ok"] = True
                        wait_signal.notify()
                        return
                    stop_event.wait(poll_interval)
            except Exception:
                pass

        thread = threading.Thread(target=_poll, name="wait-until-poll", daemon=True)
        thread.start()
        try:
            while time.monotonic() < deadline:
                self._check_cancelled(context)
                if matched["ok"]:
                    return True
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                signaled = wait_signal.wait(min(remaining, WAIT_UNTIL_CANCEL_CHECK_S))
                if matched["ok"]:
                    return True
                if signaled:
                    wait_signal.reset()
            return False
        finally:
            stop_event.set()
            thread.join(timeout=0.2)

    def _browser_wait_state_ids(
        self,
        expr: ConditionExpr,
        context: ExecutionContext,
    ) -> list[str] | None:
        if context.browser is None:
            return None

        if expr.all is not None:
            if len(expr.all) != 1:
                return None
            state_id = self._browser_condition_state_id(expr.all[0])
            return [state_id] if state_id else None

        if expr.any is not None:
            state_ids: list[str] = []
            for condition in expr.any:
                state_id = self._browser_condition_state_id(condition)
                if state_id is None:
                    return None
                state_ids.append(state_id)
            return state_ids or None

        return None

    def _browser_condition_state_id(self, condition: Condition) -> str | None:
        return browser_condition_state_id(condition)

    def _exec_goto(
        self,
        step: GotoStep,
        context: ExecutionContext,
        label_map: dict[str, int],
    ) -> None:
        self._jump_to(step.target, context, label_map)

    def _exec_stop(self, step: StopStep, workflow: str) -> dict[str, Any]:
        return {
            "ok": step.status == "success",
            "workflow": workflow,
            "status": step.status,
            "message": step.message,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # ---- Helpers ----

    def _build_label_map(self, steps: list[Step]) -> dict[str, int]:
        label_map: dict[str, int] = {}
        for i, step in enumerate(steps):
            label = getattr(step, "label", None)
            if label:
                if label in label_map:
                    raise InterpreterError(f"duplicate label: {label}")
                label_map[label] = i
        return label_map

    def _jump_to(
        self,
        label: str,
        context: ExecutionContext,
        label_map: dict[str, int],
    ) -> None:
        if label not in label_map:
            raise InterpreterError(f"unknown label: {label}")

        context.transitions += 1
        if context.transitions > MAX_TRANSITIONS:
            raise InterpreterError(
                f"max transitions ({MAX_TRANSITIONS}) exceeded — possible infinite loop"
            )
        context.pc = label_map[label]
        context.jumped = True

    def _run_with_on_fail(
        self,
        fn: Any,
        on_fail: OnFail | None,
        context: ExecutionContext,
        label_map: dict[str, int],
    ) -> ActionResult:
        """Execute fn(), applying on_fail strategy if it returns a failed result."""
        result = fn()
        if result.ok:
            return result

        if on_fail is None or on_fail.strategy == FailStrategy.abort:
            raise InterpreterError(
                f"action failed at step {context.pc}: [{result.code}] {result.message}"
            )

        assert on_fail is not None
        if on_fail.strategy == FailStrategy.skip:
            return result

        if on_fail.strategy == FailStrategy.retry:
            for _attempt in range(on_fail.retries):
                self._check_cancelled(context)
                if on_fail.delay_ms > 0:
                    time.sleep(on_fail.delay_ms / 1000.0)
                result = fn()
                if result.ok:
                    return result
            # All retries exhausted — abort
            raise InterpreterError(
                f"action failed after {on_fail.retries} retries at step {context.pc}: "
                f"[{result.code}] {result.message}"
            )

        if on_fail.strategy == FailStrategy.goto:
            if on_fail.goto is None:
                raise InterpreterError(
                    f"action failed at step {context.pc} with goto strategy but no target label"
                )
            self._jump_to(on_fail.goto, context, label_map)
            return result

        return result

    def _check_cancelled(self, context: ExecutionContext) -> None:
        checker = context.should_cancel
        if checker is None:
            return
        if bool(checker()):
            raise ExecutionCancelled("task cancelled by user")

    def _handle_on_fail(
        self,
        on_fail: OnFail,
        context: ExecutionContext,
        label_map: dict[str, int],
        message: str,
    ) -> None:
        """Handle on_fail for non-action steps (wait_until timeout)."""
        if on_fail.strategy == FailStrategy.abort:
            raise InterpreterError(message)

        if on_fail.strategy == FailStrategy.skip:
            return  # Just continue to next step

        if on_fail.strategy == FailStrategy.goto:
            if on_fail.goto is None:
                raise InterpreterError(f"{message} (on_fail goto without target label)")
            self._jump_to(on_fail.goto, context, label_map)
            return

        raise InterpreterError(message)

    def _build_session_defaults(
        self,
        payload: dict[str, Any],
        plugin_inputs: list[PluginInput],
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        target: dict[str, Any] = {}
        if isinstance(runtime, dict):
            runtime_target = runtime.get("target")
            if isinstance(runtime_target, dict):
                target = runtime_target
        defaults: dict[str, Any] = {}

        for plugin_input in plugin_inputs:
            value = payload_dict.get(plugin_input.name)
            if value is not None:
                defaults[plugin_input.name] = value
            elif plugin_input.default is not None:
                defaults[plugin_input.name] = plugin_input.default

        connection_defaults = {
            "device_ip": target.get("device_ip") or payload_dict.get("device_ip"),
            "rpa_port": target.get("rpa_port") or payload_dict.get("rpa_port"),
            "cloud_index": target.get("cloud_id") or payload_dict.get("cloud_index"),
            "device_index": target.get("device_id") or payload_dict.get("device_index"),
            "cloud_machines_per_device": payload_dict.get("cloud_machines_per_device"),
        }
        for key, value in connection_defaults.items():
            if value is not None:
                defaults[key] = value

        return defaults
