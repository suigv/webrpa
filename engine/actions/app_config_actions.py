from __future__ import annotations

from collections.abc import Mapping

from engine.action_registry import ActionMetadata
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext

_DEFAULT_ALLOWED_ACTIONS = [
    "app.ensure_running",
    "app.dismiss_popups",
    "ui.click",
    "ui.long_click",
    "ui.swipe",
    "ui.key_press",
    "ui.wait_until",
    "ai.locate_point",
]
_DEFAULT_GOAL = "探索当前 App，并沉淀可复用的基础配置骨架。"
_DEFAULT_ADVANCED_PROMPT = (
    "以安全探索为主。优先观察、关闭弹窗、切换 Tab、进入首页或公开导航页。"
    "不要登录、不要输入文本、不要发送消息、不要提交表单、不要修改设置、不要执行不可逆操作。"
)

EXPLORE_APP_CONFIG_METADATA = ActionMetadata(
    description=(
        "使用受限 agent_executor 探索当前 App，并把 selectors/states/stage_patterns/"
        "xml_filter/agent_hint 记入 app config 候选池。"
    ),
    params_schema={
        "type": "object",
        "properties": {
            "app_id": {"type": "string"},
            "app_display_name": {"type": "string"},
            "package_name": {"type": "string"},
            "goal": {"type": "string"},
            "advanced_prompt": {"type": "string"},
            "max_steps": {"type": "integer", "minimum": 1, "maximum": 40},
            "stagnant_limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["package_name"],
    },
    returns_schema={
        "type": "object",
        "properties": {
            "app_id": {"type": "string"},
            "config_path": {"type": "string"},
            "agent_status": {"type": "string"},
            "candidate_update": {"type": "object"},
        },
    },
    tags=["config", "app", "ai"],
)


def _string_param(params: Mapping[str, object], key: str) -> str:
    return str(params.get(key) or "").strip()


def _int_param(
    params: Mapping[str, object],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = params.get(key)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _string_list_param(params: Mapping[str, object], key: str) -> list[str]:
    raw = params.get(key)
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    resolved: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value and value not in resolved:
            resolved.append(value)
    return resolved


def _exploration_advanced_prompt(user_prompt: str) -> str:
    if not user_prompt:
        return _DEFAULT_ADVANCED_PROMPT
    return f"{_DEFAULT_ADVANCED_PROMPT}\n\n补充要求：{user_prompt}"


def explore_app_config_action(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from core.app_config import AppConfigManager, resolve_app_payload
    from core.golden_run_distillation import GoldenRunDistiller
    from engine.agent_executor import AgentExecutorRuntime

    app_id = _string_param(params, "app_id")
    app_display_name = _string_param(params, "app_display_name")
    package_name = _string_param(params, "package_name") or _string_param(params, "package")
    goal = _string_param(params, "goal") or _DEFAULT_GOAL
    advanced_prompt = _exploration_advanced_prompt(_string_param(params, "advanced_prompt"))
    max_steps = _int_param(params, "max_steps", default=12, minimum=1, maximum=40)
    stagnant_limit = _int_param(params, "stagnant_limit", default=4, minimum=1, maximum=20)
    allowed_actions = _string_list_param(params, "allowed_actions") or list(
        _DEFAULT_ALLOWED_ACTIONS
    )

    identity = AppConfigManager.resolve_app_identity(
        app_id=app_id,
        display_name=app_display_name,
        package_name=package_name,
    )
    resolved_package = package_name or str(identity.get("package_name") or "").strip()
    if not resolved_package:
        return ActionResult(
            ok=False,
            code="invalid_params",
            error_type=ErrorType.BUSINESS_ERROR,
            message="package_name is required for app exploration bootstrap",
        )

    ensured_identity = AppConfigManager.ensure_app_config(
        app_id=str(identity.get("app_id") or "").strip() or None,
        display_name=app_display_name or None,
        package_name=resolved_package,
    )
    resolved_app_id = str(ensured_identity.get("app_id") or "").strip()
    exploration_payload = resolve_app_payload(
        resolved_app_id,
        {
            "goal": goal,
            "app_id": resolved_app_id,
            "package": resolved_package,
            "advanced_prompt": advanced_prompt,
            "allowed_actions": allowed_actions,
            "max_steps": max_steps,
            "stagnant_limit": stagnant_limit,
            "_workflow_source": "app_config_explorer",
        },
    )

    runtime = dict(context.runtime)
    if context.emit_event is not None and "emit_event" not in runtime:
        runtime["emit_event"] = context.emit_event

    agent_runtime = AgentExecutorRuntime()
    agent_result = agent_runtime.run(
        exploration_payload,
        should_cancel=context.should_cancel,
        runtime=runtime,
    )
    trace_context = agent_runtime._trace_context(runtime)
    candidate_update = GoldenRunDistiller(
        trace_store=agent_runtime._trace_store
    ).record_app_config_learning_from_context(
        trace_context,
        snapshot_identity={
            "app_id": resolved_app_id,
            "package_name": resolved_package,
            "display_name": str(ensured_identity.get("display_name") or "").strip(),
        },
    )
    candidate_count = int(candidate_update.get("recorded") or 0)
    config_path = str(
        ensured_identity.get("path") or AppConfigManager.app_config_path(resolved_app_id)
    )
    result_data = {
        "app_id": resolved_app_id,
        "display_name": str(ensured_identity.get("display_name") or "").strip(),
        "package_name": resolved_package,
        "config_path": config_path,
        "agent_status": str(agent_result.get("status") or ""),
        "agent_result": dict(agent_result),
        "candidate_update": candidate_update,
        "trace_context": {
            "task_id": trace_context.task_id,
            "run_id": trace_context.run_id,
            "target_label": trace_context.target_label,
            "attempt_number": trace_context.attempt_number,
        },
    }

    if context.emit_event is not None:
        context.emit_event(
            "task.app_config_explorer.summary",
            {
                "app_id": resolved_app_id,
                "package_name": resolved_package,
                "agent_status": str(agent_result.get("status") or ""),
                "candidate_count": candidate_count,
            },
        )

    if bool(agent_result.get("ok")):
        return ActionResult(
            ok=True,
            code="ok",
            message=(
                f"app exploration completed; recorded {candidate_count} config candidate(s) "
                f"for {resolved_app_id or resolved_package}"
            ),
            data=result_data,
        )
    if candidate_count > 0:
        return ActionResult(
            ok=True,
            code="partial_exploration",
            message=(
                f"agent exploration ended with {str(agent_result.get('status') or 'unknown')}, "
                f"but recorded {candidate_count} config candidate(s)"
            ),
            data=result_data,
        )
    return ActionResult(
        ok=False,
        code=str(agent_result.get("code") or "app_exploration_failed"),
        error_type=ErrorType.UNKNOWN,
        message=str(agent_result.get("message") or "app exploration failed"),
        data=result_data,
    )
