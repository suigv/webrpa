from typing import Any, Dict

from engine.models.runtime import ActionResult, ExecutionContext


def llm_evaluate(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    try:
        prompt = params.get("prompt", "")
        model = params.get("model", "default")
        result = {"ok": True, "prompt": prompt, "model": model, "response": "stub"}
        return ActionResult(ok=True, code="ok", data=result)
    except Exception as e:
        return ActionResult(ok=False, code="llm_error", message=str(e))


def vlm_evaluate(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    try:
        image_data = params.get("image_data", "")
        prompt = params.get("prompt", "")
        result = {"ok": True, "image_data": image_data, "prompt": prompt, "response": "stub"}
        return ActionResult(ok=True, code="ok", data=result)
    except Exception as e:
        return ActionResult(ok=False, code="vlm_error", message=str(e))
