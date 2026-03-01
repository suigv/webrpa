from datetime import datetime, timezone
import importlib
from typing import Any, Dict

from new.engine.parser import ScriptParser


class Runner:
    def __init__(self):
        self._parser = ScriptParser()

    def run(self, script_payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._parser.parse(script_payload)
        task_name = str(plan.get("task") or "")

        if task_name == "x_auto_login":
            return self._run_plugin(task_name, script_payload, plan)

        if task_name and task_name != "anonymous":
            return {
                "ok": False,
                "task": task_name,
                "status": "failed_config_error",
                "checkpoint": "dispatch",
                "message": f"unsupported task: {task_name}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "ok": True,
            "task": task_name,
            "step_count": len(plan.get("steps", [])),
            "status": "stub_executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_plugin(self, task_name: str, payload: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        try:
            module = importlib.import_module(f"new.plugins.{task_name}")
            handler = getattr(module, "run", None)
            if not callable(handler):
                raise ValueError(f"plugin '{task_name}' missing callable run(context)")
            result = handler({"payload": payload, "plan": plan})
            if not isinstance(result, dict):
                raise ValueError("plugin result must be dict")
            result.setdefault("task", task_name)
            result.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            return result
        except Exception as exc:
            return {
                "ok": False,
                "task": task_name,
                "status": "failed_config_error",
                "checkpoint": "dispatch",
                "message": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
