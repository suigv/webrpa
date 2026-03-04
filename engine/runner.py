from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from new.engine.interpreter import Interpreter
from new.engine.parser import ScriptParser, parse_script
from new.engine.plugin_loader import PluginLoader

logger = logging.getLogger(__name__)


class Runner:
    def __init__(self) -> None:
        self._parser = ScriptParser()
        self._plugin_loader = PluginLoader()
        self._plugin_loader.scan()
        self._interpreter = Interpreter()

    def run(
        self,
        script_payload: Dict[str, Any],
        should_cancel: Callable[[], bool] | None = None,
    ) -> Dict[str, Any]:
        plan = self._parser.parse(script_payload)
        task_name = str(plan.get("task") or "")

        if should_cancel is not None and should_cancel():
            return {
                "ok": False,
                "task": task_name,
                "status": "cancelled",
                "message": "task cancelled by user",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Try YAML plugin first
        plugin = self._plugin_loader.get(task_name)
        if plugin is not None:
            return self._run_yaml_plugin(task_name, script_payload, plugin, should_cancel)

        # Unknown named task
        if task_name and task_name != "anonymous":
            return {
                "ok": False,
                "task": task_name,
                "status": "failed_config_error",
                "checkpoint": "dispatch",
                "message": f"unsupported task: {task_name}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Anonymous stub
        return {
            "ok": True,
            "task": task_name,
            "step_count": len(plan.get("steps", [])),
            "status": "stub_executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_yaml_plugin(
        self,
        task_name: str,
        payload: Dict[str, Any],
        plugin: Any,
        should_cancel: Callable[[], bool] | None = None,
    ) -> Dict[str, Any]:
        try:
            script = parse_script(plugin.script_path)
            result = self._interpreter.execute(script, payload, should_cancel=should_cancel)
            result.setdefault("task", task_name)
            result.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            return result
        except Exception as exc:
            logger.exception("plugin %s execution failed", task_name)
            return {
                "ok": False,
                "task": task_name,
                "status": "failed_config_error",
                "checkpoint": "dispatch",
                "message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
