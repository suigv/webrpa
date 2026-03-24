from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from ai_services.llm_client import LLMClient, LLMRequest
from core.account_service import list_accounts
from core.app_config import (
    AppConfigManager,
    get_app_agent_hint,
    get_app_config,
    resolve_app_payload,
)
from core.workflow_drafts import WorkflowDraftService
from engine.agent_executor import AgentExecutorRuntime

_LOGIN_KEYWORDS = (
    "login",
    "log in",
    "sign in",
    "signin",
    "登录",
    "登陆",
)


def _looks_like_login_goal(goal: str) -> bool:
    normalized = str(goal or "").strip().lower()
    return any(keyword in normalized for keyword in _LOGIN_KEYWORDS)


def _truncate_text(value: str, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _derive_display_name(goal: str, app_id: str) -> str:
    compact = _truncate_text(goal, limit=20) or "AI 任务"
    if app_id and app_id != "default":
        return f"{app_id.upper()} · {compact}"
    return compact


def _ready_accounts(app_id: str) -> list[dict[str, Any]]:
    return [
        account
        for account in list_accounts(app_id=app_id)
        if str(account.get("status") or "").strip().lower() == "ready"
    ]


def _account_strategy(selected_account: str, ready_count: int) -> str:
    if selected_account:
        return "selected"
    if ready_count > 0:
        return "pool"
    return "none"


def _account_execution_hint(
    *,
    strategy: str,
    app_id: str,
    selected_account: str,
    ready_count: int,
    is_login_goal: bool,
) -> str:
    if strategy == "selected" and selected_account:
        return f"执行方式：使用已选账号 {selected_account}。"
    if strategy == "pool":
        if is_login_goal:
            return f"执行方式：本次未指定具体账号，运行时会从 {app_id} 账号池领取 1 个可用账号。"
        return f"账号资源：当前 {app_id} 账号池有 {ready_count} 个可用账号。"
    if is_login_goal:
        return "执行方式：当前没有可用账号，登录类任务下发后大概率无法完成。"
    return "账号资源：当前未选择账号，也没有可复用的账号池资源。"


def _llm_planner_system_prompt() -> str:
    return (
        "你是 WebRPA 的 ai_dialog_planner。"
        "请根据输入生成一个简短 JSON，帮助前端确认 AI 对话任务的意图与追问。"
        "只返回 JSON 对象，字段可包含 display_name、operator_summary、missing、suggestions。"
    )


def _llm_planner_prompt(
    *,
    goal: str,
    app_id: str,
    selected_account: str,
    ready_count: int,
    advanced_prompt: str,
    expected_state_ids: list[str],
) -> str:
    payload = {
        "goal": goal,
        "app_id": app_id,
        "selected_account": selected_account or None,
        "ready_account_count": ready_count,
        "advanced_prompt": advanced_prompt or None,
        "expected_state_ids": expected_state_ids,
    }
    return json.dumps(payload, ensure_ascii=False)


class AIDialogService:
    def __init__(
        self,
        *,
        executor: AgentExecutorRuntime | None = None,
        workflow_drafts: WorkflowDraftService | None = None,
        llm_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._executor = executor or AgentExecutorRuntime()
        self._workflow_drafts = workflow_drafts or WorkflowDraftService()
        self._llm_client_factory = llm_client_factory or LLMClient

    def plan(
        self,
        *,
        goal: str,
        app_id: str | None = None,
        app_display_name: str | None = None,
        package_name: str | None = None,
        selected_account: str | None = None,
        advanced_prompt: str | None = None,
    ) -> dict[str, Any]:
        normalized_goal = str(goal or "").strip()
        if not normalized_goal:
            raise ValueError("goal is required")

        identity = AppConfigManager.resolve_app_identity(
            app_id=app_id,
            display_name=app_display_name,
            package_name=package_name,
        )
        resolved_app_id = str(identity["app_id"]).strip() or "default"
        planner_seed_payload = {
            "goal": normalized_goal,
            "app_id": resolved_app_id,
            "package": str(package_name or identity.get("package_name") or "").strip() or None,
            "advanced_prompt": str(advanced_prompt or "").strip(),
            "_workflow_source": "ai_dialog",
        }
        resolved_payload = resolve_app_payload(resolved_app_id, planner_seed_payload)
        config = self._executor.preview_config(resolved_payload)

        app_config = get_app_config(resolved_app_id)
        ready_accounts = _ready_accounts(resolved_app_id)
        ready_count = len(ready_accounts)
        selected_account_text = str(selected_account or "").strip()
        missing: list[str] = []
        suggestions: list[str] = []

        is_login_goal = _looks_like_login_goal(normalized_goal)
        strategy = _account_strategy(selected_account_text, ready_count)
        execution_hint = _account_execution_hint(
            strategy=strategy,
            app_id=resolved_app_id,
            selected_account=selected_account_text,
            ready_count=ready_count,
            is_login_goal=is_login_goal,
        )
        if is_login_goal and not selected_account_text and not ready_accounts:
            missing.append("account")
            suggestions.append("当前账号池没有可用账号，先导入或选择目标应用账号。")
        elif is_login_goal and not selected_account_text:
            suggestions.append("这是登录类任务，建议绑定账号，避免 AI 在登录页停留。")
        elif selected_account_text:
            suggestions.append(f"将优先使用已选账号 {selected_account_text}。")
        elif ready_accounts:
            suggestions.append(f"若不手动指定，后续可从 {resolved_app_id} 账号池复用可用账号。")

        if not app_config:
            suggestions.append("当前应用缺少 app 配置，将以探索模式执行。")

        operator_summary = (
            f"将以 {resolved_app_id} 应用上下文创建 AI 托管任务，"
            f"系统会自动推断状态集合并隐藏技术参数。"
        )
        llm_plan = self._plan_with_llm(
            goal=normalized_goal,
            app_id=resolved_app_id,
            selected_account=selected_account_text,
            advanced_prompt=str(advanced_prompt or "").strip(),
            expected_state_ids=list(config.expected_state_ids),
            ready_count=ready_count,
        )
        if (
            isinstance(llm_plan.get("operator_summary"), str)
            and llm_plan["operator_summary"].strip()
        ):
            operator_summary = str(llm_plan["operator_summary"]).strip()
        llm_missing = llm_plan.get("missing")
        if isinstance(llm_missing, list):
            for item in llm_missing:
                text = str(item or "").strip()
                if text and text not in missing:
                    missing.append(text)
        llm_suggestions = llm_plan.get("suggestions")
        if isinstance(llm_suggestions, list):
            for item in llm_suggestions:
                text = str(item or "").strip()
                if text and text not in suggestions:
                    suggestions.append(text)

        return {
            "display_name": str(llm_plan.get("display_name") or "").strip()
            or _derive_display_name(normalized_goal, resolved_app_id),
            "task": "agent_executor",
            "source": "ai_dialog",
            "operator_summary": operator_summary,
            "resolved_app": {
                "app_id": resolved_app_id,
                "name": str(
                    app_config.get("display_name")
                    or identity.get("display_name")
                    or resolved_app_id
                ).strip(),
                "package": str(resolved_payload.get("package") or "").strip() or None,
                "has_app_config": bool(app_config),
                "agent_hint": get_app_agent_hint(resolved_app_id) or None,
            },
            "resolved_payload": {
                **resolved_payload,
                "expected_state_ids": list(config.expected_state_ids),
                "allowed_actions": list(config.allowed_actions),
                "max_steps": int(config.max_steps),
                "stagnant_limit": int(config.stagnant_limit),
            },
            "follow_up": {
                "missing": missing,
                "suggestions": suggestions,
                "message": suggestions[0] if suggestions else "",
            },
            "account": {
                "selected_account": selected_account_text or None,
                "ready_count": ready_count,
                "strategy": strategy,
                "execution_hint": execution_hint,
                "requires_account": is_login_goal,
                "can_execute": not (is_login_goal and strategy == "none"),
            },
        }

    def list_history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._workflow_drafts.list_ai_dialog_history(limit=limit)

    def _plan_with_llm(
        self,
        *,
        goal: str,
        app_id: str,
        selected_account: str,
        advanced_prompt: str,
        expected_state_ids: list[str],
        ready_count: int,
    ) -> dict[str, Any]:
        client = self._llm_client_factory()
        request = LLMRequest(
            prompt=_llm_planner_prompt(
                goal=goal,
                app_id=app_id,
                selected_account=selected_account,
                ready_count=ready_count,
                advanced_prompt=advanced_prompt,
                expected_state_ids=expected_state_ids,
            ),
            system_prompt=_llm_planner_system_prompt(),
            response_format={"type": "json_object"},
            options={"temperature": 0.1},
            metadata={"feature": "ai_dialog_planner"},
        )
        try:
            response = client.evaluate(request)
        except Exception:
            return {}
        if not getattr(response, "ok", False):
            return {}
        text = str(getattr(response, "output_text", "") or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
