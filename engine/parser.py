from typing import Any, Dict, List


class ScriptParser:
    def parse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task = str(payload.get("task") or "anonymous")
        steps = payload.get("steps")
        if not isinstance(steps, list):
            steps = []
        normalized_steps: List[Dict[str, Any]] = []
        for index, step in enumerate(steps):
            if isinstance(step, dict):
                action = str(step.get("action") or f"noop_{index}")
                params = step.get("params") if isinstance(step.get("params"), dict) else {}
            else:
                action = f"noop_{index}"
                params = {}
            normalized_steps.append({"action": action, "params": params})
        return {"task": task, "steps": normalized_steps}
