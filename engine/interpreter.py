from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engine.action_registry import get_registry, register_defaults
from engine.conditions import browser_condition_state_id, evaluate as eval_condition
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.workflow import (
    ActionStep,
    Condition,
    ConditionExpr,
    ConditionType,
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


class InterpreterError(Exception):
    """Raised when the interpreter encounters an unrecoverable error."""


class InterpreterCancelled(Exception):
    pass


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
        payload: Dict[str, Any],
        should_cancel: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a workflow script with the given payload.

        Returns a result dict with ok, status, message, and workflow metadata.
        """
        context = ExecutionContext(payload=payload)
        context.should_cancel = should_cancel
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
            return {
                "ok": True,
                "workflow": script.workflow,
                "status": "completed",
                "message": "workflow finished",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except InterpreterError as exc:
            return {
                "ok": False,
                "workflow": script.workflow,
                "status": "failed",
                "message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except InterpreterCancelled as exc:
            return {
                "ok": False,
                "workflow": script.workflow,
                "status": "cancelled",
                "message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.exception("interpreter unexpected error")
            return {
                "ok": False,
                "workflow": script.workflow,
                "status": "error",
                "message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            try:
                from engine.actions.ui_actions import release_selector_context

                _ = release_selector_context(context)
            except Exception:
                logger.debug("failed to release selector context", exc_info=True)
            if context.browser is not None:
                try:
                    context.browser.close()
                except Exception:
                    pass
                context.browser = None

    # ---- Step executors ----

    def _exec_action(
        self,
        step: ActionStep,
        context: ExecutionContext,
        registry: Any,
        label_map: Dict[str, int],
    ) -> None:
        interp_ctx = {"payload": context.payload, "vars": context.vars}
        params = interpolate_params(step.params, interp_ctx)

        handler = registry.resolve(step.action)
        result = self._run_with_on_fail(
            lambda: handler(params, context),
            step.on_fail,
            context,
            label_map,
        )
        context.last_result = result

        if step.save_as:
            context.vars[step.save_as] = result.data if result.data else {
                "ok": result.ok,
                "code": result.code,
                "message": result.message,
            }

    def _exec_if(
        self,
        step: IfStep,
        context: ExecutionContext,
        label_map: Dict[str, int],
    ) -> None:
        matched = eval_condition(step.when, context)
        target = step.then if matched else step.otherwise
        if target is not None:
            self._jump_to(target, context, label_map)

    def _exec_wait_until(
        self,
        step: WaitUntilStep,
        context: ExecutionContext,
        label_map: Dict[str, int],
    ) -> None:
        timeout_s = min(step.timeout_ms / 1000.0, WAIT_UNTIL_HARD_LIMIT_S)
        timeout_ms = int(timeout_s * 1000)
        interval_s = step.interval_ms / 1000.0
        service_state_ids = self._browser_wait_state_ids(step.check, context)
        if service_state_ids:
            try:
                result = BrowserUIStateService().wait_until(
                    context,
                    expected_state_ids=service_state_ids,
                    timeout_ms=timeout_ms,
                    interval_ms=step.interval_ms,
                )
                if result.ok:
                    return
                if result.code == "timeout":
                    on_fail = step.on_timeout or step.on_fail
                    if on_fail:
                        self._handle_on_fail(on_fail, context, label_map, "wait_until timed out")
                    else:
                        raise InterpreterError(
                            f"wait_until timed out after {timeout_s:.1f}s at step "
                            f"{context.pc} ({step.label or 'unlabeled'})"
                        )
                    return
            except Exception:
                logger.debug("service-backed wait_until failed; falling back to polling", exc_info=True)

        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            self._check_cancelled(context)
            if eval_condition(step.check, context):
                return
            time.sleep(interval_s)

        # Timed out
        on_fail = step.on_timeout or step.on_fail
        if on_fail:
            self._handle_on_fail(on_fail, context, label_map, "wait_until timed out")
        else:
            raise InterpreterError(
                f"wait_until timed out after {timeout_s:.1f}s at step "
                f"{context.pc} ({step.label or 'unlabeled'})"
            )

    def _browser_wait_state_ids(
        self,
        expr: ConditionExpr,
        context: ExecutionContext,
    ) -> List[str] | None:
        if context.browser is None:
            return None

        if expr.all is not None:
            if len(expr.all) != 1:
                return None
            state_id = self._browser_condition_state_id(expr.all[0])
            return [state_id] if state_id else None

        if expr.any is not None:
            state_ids: List[str] = []
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
        label_map: Dict[str, int],
    ) -> None:
        self._jump_to(step.target, context, label_map)

    def _exec_stop(self, step: StopStep, workflow: str) -> Dict[str, Any]:
        return {
            "ok": step.status == "success",
            "workflow": workflow,
            "status": step.status,
            "message": step.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ---- Helpers ----

    def _build_label_map(self, steps: List[Step]) -> Dict[str, int]:
        label_map: Dict[str, int] = {}
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
        label_map: Dict[str, int],
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
        on_fail: Optional[OnFail],
        context: ExecutionContext,
        label_map: Dict[str, int],
    ) -> ActionResult:
        """Execute fn(), applying on_fail strategy if it returns a failed result."""
        result = fn()
        if result.ok:
            return result

        if on_fail is None or on_fail.strategy == FailStrategy.abort:
            raise InterpreterError(
                f"action failed at step {context.pc}: [{result.code}] {result.message}"
            )

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
            raise InterpreterCancelled("task cancelled by user")

    def _handle_on_fail(
        self,
        on_fail: OnFail,
        context: ExecutionContext,
        label_map: Dict[str, int],
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
