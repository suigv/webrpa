from typing import Dict


def llm_evaluate(params: Dict[str, object]) -> Dict[str, object]:
    return {"ok": True, "action": "llm_evaluate", "params": params, "result": "stub"}


def vlm_evaluate(params: Dict[str, object]) -> Dict[str, object]:
    return {"ok": True, "action": "vlm_evaluate", "params": params, "result": "stub"}
