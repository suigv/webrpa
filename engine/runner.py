from datetime import datetime, timezone
from typing import Any, Dict

from new.engine.parser import ScriptParser


class Runner:
    def __init__(self):
        self._parser = ScriptParser()

    def run(self, script_payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._parser.parse(script_payload)
        return {
            "ok": True,
            "task": plan.get("task"),
            "step_count": len(plan.get("steps", [])),
            "status": "stub_executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
