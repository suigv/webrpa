from __future__ import annotations
import time
from typing import Any, Dict
from engine.actions import _rpc_bootstrap
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc
from engine.action_registry import ActionMetadata

INPUT_TEXT_METADATA = ActionMetadata(
    description="在当前焦点处输入文本",
    params_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要输入的文本内容"}
        },
        "required": ["text"]
    },
    tags=["skill"]
)

KEY_PRESS_METADATA = ActionMetadata(
    description="模拟按下系统按键",
    params_schema={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "enum": ["back", "home", "enter", "recent"],
                "description": "按键名称"
            }
        },
        "required": ["key"]
    }
)

KEY_CODE_MAP = {
    "back": 4,
    "home": 3,
    "enter": 66,
    "recent": 82,
}

def _get_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    return _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=_rpc_bootstrap.is_rpc_enabled,
        resolve_params=_rpc_bootstrap.resolve_connection_params,
        rpc_factory=MytRpc,
        result_factory=ActionResult,
    )

def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)

def input_text(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        text = str(params.get("text") or "")
        if not text:
            return ActionResult(ok=False, code="invalid_params", message="text is required")
        
        helper = context.humanized
        if helper is None or not helper.config.enabled:
            ok = rpc.sendText(text) if rpc is not None else False
            return ActionResult(ok=ok, code="ok" if ok else "send_text_failed")
            
        sequence = helper.get_typing_sequence(text)
        if context.emit_event:
            delays = [d for _, d in sequence if d > 0]
            avg_delay = sum(delays)/len(delays) if delays else 0
            context.emit_event("humanized.typing", {"text_length": len(text), "avg_delay_ms": int(avg_delay * 1000)})

        ok = True
        for char, delay in sequence:
            context.check_cancelled()
            if delay > 0:
                time.sleep(delay)
            char_ok = rpc.sendText(char) if rpc is not None else False
            if not char_ok:
                ok = False
                break
        return ActionResult(ok=ok, code="ok" if ok else "send_text_failed")
    finally:
        _close_rpc(rpc)

def key_press(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        key = str(params.get("key", "")).lower()
        code = KEY_CODE_MAP.get(key)
        if code is None:
            return ActionResult(ok=False, code="invalid_key", message=f"unsupported key: {key}")
        ok = rpc.keyPress(code) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "key_press_failed", data={"key": key, "code": code})
    finally:
        _close_rpc(rpc)
