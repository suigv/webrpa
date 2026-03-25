from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from ai_services.llm_client import LLMClient, LLMRequest
from core.account_service import list_accounts
from core.app_branch_service import AppBranchProfileService
from core.app_config import (
    AppConfigManager,
    get_app_agent_hint,
    get_app_config,
    resolve_app_payload,
)
from core.business_profile import (
    DEFAULT_BRANCH_ID,
    branch_label,
    normalize_branch_id,
    resolve_branch_profile,
)
from core.control_flow_hints import analyze_control_flow_prompt
from core.task_semantics import (
    build_memory_reuse_plan,
    infer_intent,
    memory_hint_for_reason,
    normalize_goal_text,
)
from core.workflow_drafts import WorkflowDraftService
from engine.agent_executor import AgentExecutorRuntime
from engine.models.declarative_script import (
    ConsumeItem,
    ConsumeKind,
    ConsumeSource,
    DeclarativeScriptKind,
    DeclarativeScriptRole,
    DeclarativeScriptV0,
    DeclarativeScriptVersion,
    FailureDefinition,
    HandoffAction,
    HandoffPolicy,
    ProduceItem,
    ProduceKind,
    StageItem,
    StageKind,
    TerminalDefinition,
)
from engine.models.manifest import PluginManifest
from engine.plugin_loader import get_shared_plugin_loader

_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def _collapse_ws(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def _normalized_goal_text(value: str) -> str:
    return normalize_goal_text(value)


def _truncate_text(value: str, *, limit: int) -> str:
    text = _collapse_ws(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _derive_display_name(goal: str, app_id: str) -> str:
    compact = _truncate_text(goal, limit=20) or "AI 任务"
    if app_id and app_id != "default":
        return f"{app_id.upper()} · {compact}"
    return compact


def _infer_intent(goal: str) -> dict[str, Any]:
    return infer_intent(goal)


def _recommended_title(app_name: str, intent: dict[str, Any], goal: str, app_id: str) -> str:
    label = str(intent.get("label") or "").strip()
    if app_name and label and str(intent.get("objective") or "") != "exploration":
        return f"{app_name} {label}"
    return _derive_display_name(goal, app_id)


def _manifest_declared_app_id(manifest: PluginManifest) -> str:
    for item in manifest.inputs:
        if item.name == "app_id":
            return str(item.default or "").strip().lower()
    return ""


def _manifest_text(manifest: PluginManifest) -> str:
    parts = [
        manifest.name,
        manifest.display_name,
        manifest.category,
        manifest.description,
    ]
    for item in manifest.inputs:
        parts.extend(
            [
                item.name,
                str(item.label or ""),
                str(item.description or ""),
                str(item.placeholder or ""),
            ]
        )
    return _normalized_goal_text(" ".join(part for part in parts if part))


def _resolve_app_tokens(
    *,
    app_id: str,
    identity: dict[str, Any],
    app_config: dict[str, Any],
) -> list[str]:
    values = [
        app_id,
        str(identity.get("display_name") or ""),
        str(app_config.get("display_name") or ""),
        *(str(item or "") for item in app_config.get("aliases") or []),
    ]
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalized_goal_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        tokens.append(text)
    return tokens


def _score_plugin_for_app(
    manifest: PluginManifest,
    *,
    app_id: str,
    app_tokens: list[str],
) -> int:
    _ = app_tokens
    declared_app_id = _manifest_declared_app_id(manifest)
    if declared_app_id:
        if declared_app_id != app_id:
            return -1
        return 8
    if manifest.name.startswith(f"{app_id}_"):
        return 6
    return 0


def _score_plugin_for_intent(
    manifest: PluginManifest,
    *,
    intent: dict[str, Any],
    normalized_goal: str,
) -> tuple[int, list[str]]:
    if str(intent.get("objective") or "") == "exploration":
        return 0, []
    manifest_text = _manifest_text(manifest)
    matched: list[str] = []
    score = 0
    for token in tuple(intent.get("plugin_keywords") or ()):
        keyword = str(token or "").strip().lower()
        if keyword and keyword in manifest_text and keyword not in matched:
            matched.append(keyword)
            score += 3
    for token in tuple(intent.get("matched_keywords") or ()):
        keyword = str(token or "").strip().lower()
        if keyword and keyword in manifest_text and keyword not in matched:
            matched.append(keyword)
            score += 1
    if manifest.display_name and _normalized_goal_text(manifest.display_name) in normalized_goal:
        score += 2
    return score, matched


def _fit_label(score: int) -> str:
    if score >= 13:
        return "high"
    if score >= 9:
        return "medium"
    return "low"


def _decl_identifier(value: str, *, default: str) -> str:
    normalized = _NON_WORD_RE.sub("_", str(value or "").strip().lower()).strip("_")
    if not normalized:
        return default
    if normalized[0].isdigit():
        normalized = f"{default}_{normalized}"
    return normalized[:64]


def _declarative_role(task_name: str, objective: str) -> DeclarativeScriptRole:
    task = str(task_name or "").strip().lower()
    objective_value = str(objective or "").strip().lower()
    if objective_value == "login" or task.endswith("login"):
        return DeclarativeScriptRole.login
    if objective_value == "scrape_blogger" or "scrape" in task:
        return DeclarativeScriptRole.collect
    if objective_value == "reply_dm" or "reply" in task:
        return DeclarativeScriptRole.reply
    if "nurture" in task:
        return DeclarativeScriptRole.nurture
    if "follow" in task or objective_value in {"follow_followers", "quote_intercept"}:
        return DeclarativeScriptRole.engage
    return DeclarativeScriptRole.utility


def _app_scope_for_role(role: DeclarativeScriptRole) -> str:
    return {
        DeclarativeScriptRole.login: "auth",
        DeclarativeScriptRole.collect: "discovery",
        DeclarativeScriptRole.filter: "discovery",
        DeclarativeScriptRole.nurture: "maintenance",
        DeclarativeScriptRole.engage: "engagement",
        DeclarativeScriptRole.reply: "messaging",
        DeclarativeScriptRole.summarize: "maintenance",
        DeclarativeScriptRole.utility: "maintenance",
    }.get(role, "maintenance")


def _declarative_depends_on(app_id: str, role: DeclarativeScriptRole) -> list[str]:
    if role == DeclarativeScriptRole.login:
        return []
    app_key = _decl_identifier(app_id, default="app")
    return [f"{app_key}_login_decl"]


def _consume_items_for_manifest(
    manifest: PluginManifest | None,
    *,
    role: DeclarativeScriptRole,
    branch_id: str,
    needs_shared_resource: bool,
) -> list[ConsumeItem]:
    items: list[ConsumeItem] = []
    seen: set[str] = set()

    def _append(
        name: str,
        *,
        kind: ConsumeKind,
        description: str,
        required: bool,
        source: ConsumeSource,
    ) -> None:
        safe_name = _decl_identifier(name, default="input")
        if safe_name in seen:
            return
        seen.add(safe_name)
        items.append(
            ConsumeItem(
                name=safe_name,
                kind=kind,
                description=description,
                required=required,
                source=source,
            )
        )

    if role != DeclarativeScriptRole.login:
        _append(
            "login_state",
            kind=ConsumeKind.state,
            description="账号已登录且处于可进入目标 App 页面的状态",
            required=True,
            source=ConsumeSource.runtime_state,
        )

    if branch_id:
        _append(
            "branch_policy",
            kind=ConsumeKind.policy,
            description="当前业务分支的默认策略与限制配置",
            required=True,
            source=ConsumeSource.branch_policy,
        )

    if needs_shared_resource:
        _append(
            "shared_resource",
            kind=ConsumeKind.resource,
            description="该脚本依赖的共享资源池或共享候选对象",
            required=True,
            source=ConsumeSource.shared_resource,
        )

    if manifest is None:
        return items

    for input_item in manifest.inputs:
        if input_item.name in {"app_id"}:
            continue
        if input_item.name == "branch_id":
            _append(
                "branch_policy",
                kind=ConsumeKind.policy,
                description=str(input_item.description or "业务分支策略配置"),
                required=bool(input_item.required),
                source=ConsumeSource.branch_policy,
            )
            continue
        kind = ConsumeKind.policy if input_item.name in {"resource_namespace"} else ConsumeKind.input
        source = (
            ConsumeSource.system_default
            if input_item.system or input_item.default not in (None, "", [], {})
            else ConsumeSource.user_input
        )
        _append(
            input_item.name,
            kind=kind,
            description=str(input_item.description or input_item.label or input_item.name),
            required=bool(input_item.required),
            source=source,
        )

    return items


def _produce_items_for_task(
    task_name: str,
    *,
    role: DeclarativeScriptRole,
) -> list[ProduceItem]:
    task = str(task_name or "").strip().lower()
    if role == DeclarativeScriptRole.login:
        return [
            ProduceItem(
                name="login_state",
                kind=ProduceKind.artifact,
                description="当前 App 可供后续脚本复用的登录态",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="login_summary",
                kind=ProduceKind.result,
                description="本轮登录结果摘要",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="auth_challenge_signal",
                kind=ProduceKind.signal,
                description="登录过程中产生的验证码或风控信号",
                persistent=False,
                exposed=True,
            ),
        ]
    if "scrape" in task:
        return [
            ProduceItem(
                name="blogger_candidates",
                kind=ProduceKind.resource,
                description="当前脚本新增到候选池中的博主候选",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="scrape_summary",
                kind=ProduceKind.result,
                description="本轮采集统计摘要",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="candidate_pool_ready",
                kind=ProduceKind.signal,
                description="候选池已具备后续脚本消费条件",
                persistent=False,
                exposed=True,
            ),
        ]
    if "follow" in task:
        return [
            ProduceItem(
                name="follow_summary",
                kind=ProduceKind.result,
                description="本轮关注统计结果",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="followed_targets",
                kind=ProduceKind.artifact,
                description="本轮已处理的目标记录",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="follow_limit_reached",
                kind=ProduceKind.signal,
                description="当前轮次或当日关注上限已触发",
                persistent=False,
                exposed=True,
            ),
        ]
    if role == DeclarativeScriptRole.reply:
        return [
            ProduceItem(
                name="reply_summary",
                kind=ProduceKind.result,
                description="本轮回复处理摘要",
                persistent=True,
                exposed=True,
            ),
            ProduceItem(
                name="replied_targets",
                kind=ProduceKind.artifact,
                description="本轮已处理的对话或目标记录",
                persistent=True,
                exposed=True,
            ),
        ]
    return [
        ProduceItem(
            name=f"{_decl_identifier(task_name, default='script')}_summary",
            kind=ProduceKind.result,
            description="该脚本执行后的结果摘要",
            persistent=True,
            exposed=True,
        )
    ]


def _stage_items_for_role(
    *,
    role: DeclarativeScriptRole,
    title: str,
) -> list[StageItem]:
    common_wait = HandoffPolicy(
        allowed=True,
        triggers=["页面状态不明确", "异常弹窗无法自动处理"],
        on_handoff=HandoffAction.pause_and_wait,
    )
    if role == DeclarativeScriptRole.login:
        return [
            StageItem(
                name="prepare_auth_flow",
                title="准备登录流程",
                description=f"为 {title} 建立可执行的登录前置环境。",
                kind=StageKind.setup,
                goal="进入可尝试登录的准备态",
                exit_when=["已进入登录页", "已识别为已登录状态"],
                handoff_policy=common_wait,
            ),
            StageItem(
                name="check_auth_state",
                title="判断登录状态",
                description="判断当前是否已经处于可复用登录态，或需要继续登录。",
                kind=StageKind.decision,
                goal="明确当前登录分支",
                exit_when=["已确认已登录", "已确认需要继续登录", "触发人工接管"],
                handoff_policy=common_wait,
            ),
            StageItem(
                name="finish_auth_flow",
                title="结束登录流程",
                description="输出登录结果并结束脚本。",
                kind=StageKind.finalize,
                goal="完成登录脚本终态输出",
                exit_when=["登录结果输出完成"],
                handoff_policy=HandoffPolicy(
                    allowed=False,
                    triggers=[],
                    on_handoff=HandoffAction.record_and_fail,
                ),
            ),
        ]
    if role in {
        DeclarativeScriptRole.collect,
        DeclarativeScriptRole.nurture,
        DeclarativeScriptRole.engage,
        DeclarativeScriptRole.reply,
    }:
        return [
            StageItem(
                name="prepare_flow",
                title="准备执行流程",
                description=f"为 {title} 建立可执行的页面、账号和资源前置条件。",
                kind=StageKind.setup,
                goal="进入可执行主动作的准备态",
                exit_when=["已进入目标页面", "检测到提前退出条件", "触发人工接管"],
                handoff_policy=common_wait,
            ),
            StageItem(
                name="main_loop",
                title="循环执行主体",
                description=f"围绕 {title} 的主目标持续执行，直到达成目标或触发退出条件。",
                kind=StageKind.loop,
                goal="完成本轮主任务目标",
                exit_when=["达到目标", "没有更多可执行对象", "触发人工接管", "连续失败过多"],
                handoff_policy=HandoffPolicy(
                    allowed=True,
                    triggers=["页面状态无法判断", "异常弹窗无法自动处理"],
                    on_handoff=HandoffAction.pause_and_exit,
                ),
            ),
            StageItem(
                name="finalize_flow",
                title="结束执行流程",
                description="汇总本轮结果并完成脚本退出。",
                kind=StageKind.finalize,
                goal="输出本轮执行结果",
                exit_when=["结果输出完成"],
                handoff_policy=HandoffPolicy(
                    allowed=False,
                    triggers=[],
                    on_handoff=HandoffAction.record_and_fail,
                ),
            ),
        ]
    return [
        StageItem(
            name="run_flow",
            title="执行流程",
            description=f"完成 {title} 的主要任务目标。",
            kind=StageKind.setup,
            goal="完成当前脚本主要目标",
            exit_when=["脚本目标已达成", "触发退出条件"],
            handoff_policy=common_wait,
        )
    ]


def _success_definition_for_role(role: DeclarativeScriptRole, title: str) -> TerminalDefinition:
    if role == DeclarativeScriptRole.login:
        return TerminalDefinition(
            summary="成功进入已登录且可供后续脚本消费的状态",
            signals=["进入已登录可操作状态", "输出登录结果摘要"],
        )
    return TerminalDefinition(
        summary=f"完成“{title}”的直接目标并输出结果摘要",
        signals=["阶段目标达成", "结果摘要输出完成"],
    )


def _failure_definition_for_role(role: DeclarativeScriptRole, title: str) -> FailureDefinition:
    retryable = role != DeclarativeScriptRole.utility
    return FailureDefinition(
        summary=f"无法完成“{title}”或进入不可自动恢复异常态",
        signals=["进入异常态", "连续失败过多", "人工终止"],
        retryable=retryable,
    )


def _top_handoff_policy_for_role(role: DeclarativeScriptRole) -> HandoffPolicy:
    triggers = ["验证码", "风控验证", "页面状态不明确"] if role == DeclarativeScriptRole.login else [
        "页面状态不明确",
        "异常弹窗无法自动处理",
    ]
    return HandoffPolicy(
        allowed=True,
        triggers=triggers,
        on_handoff=HandoffAction.pause_and_wait,
    )


def _declarative_scripts_for_workflows(
    *,
    app_id: str,
    intent: dict[str, Any],
    branch: dict[str, Any],
    workflows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    loader = get_shared_plugin_loader()
    branch_id = str(branch.get("branch_id") or "").strip()
    for workflow in workflows:
        task_name = str(workflow.get("task") or "").strip()
        if not task_name or task_name == "agent_executor":
            continue
        entry = loader.get(task_name)
        manifest = entry.manifest if entry is not None else None
        role = _declarative_role(task_name, str(intent.get("objective") or ""))
        title = str(
            workflow.get("display_name")
            or (manifest.display_name if manifest is not None else "")
            or task_name
        ).strip()
        description = str(
            (manifest.description if manifest is not None else "")
            or intent.get("expected_outcome")
            or title
        ).strip()
        app_key = _decl_identifier(app_id, default="app")
        script = DeclarativeScriptV0(
            version=DeclarativeScriptVersion.v0,
            kind=DeclarativeScriptKind.declarative_script,
            app_id=app_key,
            app_scope=_app_scope_for_role(role),
            name=f"{_decl_identifier(task_name, default='script')}_decl",
            title=title[:40] or task_name,
            description=description[:200] or title,
            goal=str(intent.get("label") or title)[:120],
            role=role,
            consumes=_consume_items_for_manifest(
                manifest,
                role=role,
                branch_id=branch_id,
                needs_shared_resource=bool(workflow.get("requires_shared_resource")),
            ),
            produces=_produce_items_for_task(task_name, role=role),
            depends_on=_declarative_depends_on(app_key, role),
            stages=_stage_items_for_role(role=role, title=title),
            success_definition=_success_definition_for_role(role, title),
            failure_definition=_failure_definition_for_role(role, title),
            handoff_policy=_top_handoff_policy_for_role(role),
        )
        results.append(script.model_dump(mode="json"))
    return results


def _planner_declarative_context(
    scripts: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_scripts: list[dict[str, Any]] = []
    summary_parts: list[str] = []
    stage_hints: list[dict[str, Any]] = []

    for script in scripts[:4]:
        if not isinstance(script, Mapping):
            continue
        title = str(script.get("title") or script.get("name") or "").strip()
        goal = str(script.get("goal") or "").strip()
        role = str(script.get("role") or "").strip()
        stages_raw = script.get("stages")
        stages = stages_raw if isinstance(stages_raw, list) else []
        normalized_scripts.append(dict(script))

        stage_titles = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in stages
            if isinstance(item, Mapping)
            and str(item.get("title") or item.get("name") or "").strip()
        ]
        if title:
            summary = title
            if role:
                summary = f"{summary}（{role}）"
            if goal and goal != title:
                summary = f"{summary}：{goal}"
            if stage_titles:
                summary = f"{summary}；阶段：{' -> '.join(stage_titles[:4])}"
            summary_parts.append(summary)

        for stage in stages[:6]:
            if not isinstance(stage, Mapping):
                continue
            stage_title = str(stage.get("title") or stage.get("name") or "").strip()
            if not stage_title:
                continue
            stage_hints.append(
                {
                    "script_name": str(script.get("name") or "").strip(),
                    "script_title": title,
                    "stage_name": str(stage.get("name") or "").strip(),
                    "stage_title": stage_title,
                    "kind": str(stage.get("kind") or "").strip(),
                    "goal": str(stage.get("goal") or "").strip(),
                    "exit_when": list(stage.get("exit_when") or []),
                }
            )

    return {
        "_planner_declarative_scripts": normalized_scripts,
        "_planner_declarative_summary": _truncate_text(" | ".join(summary_parts), limit=500),
        "_planner_stage_hints": stage_hints[:12],
    }


def _workflow_reason(
    *,
    intent: dict[str, Any],
    matched: list[str],
    branch_id: str,
    needs_shared_resource: bool,
) -> str:
    reasons: list[str] = []
    if matched:
        reasons.append(f"匹配关键词：{', '.join(matched[:3])}")
    if branch_id and normalize_branch_id(branch_id, default="") not in ("", DEFAULT_BRANCH_ID):
        reasons.append(f"可直接复用分支 {branch_id}")
    if needs_shared_resource:
        reasons.append("该类任务通常依赖已有共享资源池")
    fallback = str(intent.get("expected_outcome") or "").strip()
    return "；".join(reasons) or fallback


def _recommended_workflows(
    *,
    app_id: str,
    app_tokens: list[str],
    has_app_config: bool,
    intent: dict[str, Any],
    branch_id: str,
    normalized_goal: str,
) -> list[dict[str, Any]]:
    results: list[tuple[int, dict[str, Any]]] = []
    loader = get_shared_plugin_loader()
    for name in loader.names:
        entry = loader.get(name)
        if entry is None:
            continue
        manifest = entry.manifest
        app_score = _score_plugin_for_app(manifest, app_id=app_id, app_tokens=app_tokens)
        if app_score <= 0:
            continue
        intent_score, matched = _score_plugin_for_intent(
            manifest,
            intent=intent,
            normalized_goal=normalized_goal,
        )
        total_score = app_score + intent_score
        if total_score <= 0:
            continue
        results.append(
            (
                total_score,
                {
                    "task": manifest.name,
                    "display_name": manifest.display_name,
                    "category": manifest.category,
                    "fit": _fit_label(total_score),
                    "kind": "plugin",
                    "score": total_score,
                    "reason": _workflow_reason(
                        intent=intent,
                        matched=matched,
                        branch_id=branch_id,
                        needs_shared_resource=bool(intent.get("needs_shared_resource")),
                    ),
                    "requires_shared_resource": bool(intent.get("needs_shared_resource")),
                },
            )
        )
    results.sort(key=lambda item: (-item[0], item[1]["task"]))
    workflows = [item for _, item in results[:3]]
    agent_reason = (
        "当前会以下发 AI 托管任务为主，先完成一次可观测执行，再决定是否收敛为固定插件。"
        if has_app_config
        else "当前应用缺少完整共享配置，建议先用 AI 探索执行并沉淀 app 骨架。"
    )
    workflows.insert(
        0,
        {
            "task": "agent_executor",
            "display_name": "AI 探索执行",
            "category": "AI",
            "fit": "high" if not workflows or workflows[0]["fit"] != "high" else "medium",
            "kind": "agent",
            "reason": agent_reason,
            "requires_shared_resource": False,
        },
    )
    return workflows[:4]


def _selected_account_record(accounts: list[dict[str, Any]], selected_account: str) -> dict[str, Any] | None:
    selected = str(selected_account or "").strip()
    if not selected:
        return None
    for account in accounts:
        if str(account.get("account") or "").strip() == selected:
            return account
    return None


def _ready_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        account
        for account in accounts
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
    requires_account: bool,
) -> str:
    if strategy == "selected" and selected_account:
        return f"执行方式：使用已选账号 {selected_account}。"
    if strategy == "pool":
        return f"执行方式：未绑定具体账号，运行时会从 {app_id} 账号池领取 1 个可用账号（当前 {ready_count} 个就绪）。"
    if requires_account:
        return f"执行方式：当前没有可用账号，先导入或选择 {app_id} 账号后再执行。"
    return "执行方式：当前任务不强制要求账号，可先以探索模式执行。"


def _branch_snapshot(
    *,
    app_id: str,
    goal: str,
    selected_account_record: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        snapshot = AppBranchProfileService().get_profiles(app_id)
    except Exception:
        snapshot = {
            "app_id": app_id,
            "display_name": app_id.upper(),
            "default_branch": DEFAULT_BRANCH_ID,
            "branches": resolve_branch_profile(app_id=app_id)["branches"],
        }
    goal_text = _normalized_goal_text(goal)
    inferred_goal_branch = ""
    inferred_goal_token = ""
    for item in snapshot.get("branches") or []:
        if not isinstance(item, dict):
            continue
        branch_id = normalize_branch_id(item.get("branch_id"), default="")
        label = _normalized_goal_text(item.get("label") or "")
        if branch_id and branch_id in goal_text:
            inferred_goal_branch = branch_id
            inferred_goal_token = branch_id
            break
        if label and label in goal_text:
            inferred_goal_branch = branch_id
            inferred_goal_token = str(item.get("label") or "").strip()
            break
    account_default_branch = normalize_branch_id(
        selected_account_record.get("default_branch") if isinstance(selected_account_record, dict) else "",
        default="",
    )
    resolved = resolve_branch_profile(
        app_id=app_id,
        requested_branch=inferred_goal_branch or None,
        account_default_branch=account_default_branch or None,
    )
    profile = {}
    for item in snapshot.get("branches") or []:
        if normalize_branch_id(item.get("branch_id"), default="") == resolved["branch_id"]:
            profile = dict(item)
            break
    source = "app_default"
    if inferred_goal_branch:
        source = "goal"
    elif account_default_branch:
        source = "account_default"
    options = []
    for item in resolved.get("branches") or []:
        if not isinstance(item, dict):
            continue
        options.append(
            {
                "branch_id": normalize_branch_id(item.get("branch_id")),
                "label": str(item.get("label") or branch_label(item.get("branch_id"))).strip(),
                "is_default": bool(item.get("is_default")),
            }
        )
    payload_defaults = dict(profile.get("payload_defaults") or {})
    return {
        "branch_id": resolved["branch_id"],
        "label": str(profile.get("label") or resolved.get("label") or branch_label(resolved["branch_id"])).strip(),
        "default_branch": resolved["default_branch"],
        "source": source,
        "source_detail": inferred_goal_token or None,
        "options": options,
        "search_keyword_count": len(profile.get("search_keywords") or []),
        "reply_text_count": len(profile.get("reply_texts") or []),
        "resource_namespace": str(profile.get("resource_namespace") or "").strip() or None,
        "reply_ai_type": str(profile.get("reply_ai_type") or "").strip() or None,
        "payload_defaults": payload_defaults,
        "notes": str(profile.get("notes") or "").strip() or None,
        "needs_confirmation": len(options) > 1 and source == "app_default",
    }


def _apply_branch_context(
    *,
    resolved_payload: dict[str, Any],
    intent: dict[str, Any],
    branch: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(resolved_payload)
    branch_id = normalize_branch_id(branch.get("branch_id"))
    if branch_id:
        payload["branch_id"] = branch_id
    if intent.get("needs_shared_resource") and branch.get("resource_namespace"):
        payload.setdefault("resource_namespace", branch["resource_namespace"])
    if intent.get("expects_reply_strategy") and branch.get("reply_ai_type"):
        payload.setdefault("reply_ai_type", branch["reply_ai_type"])
    payload_defaults = dict(branch.get("payload_defaults") or {})
    for key, value in payload_defaults.items():
        if key not in payload or payload.get(key) in (None, "", [], {}):
            payload[key] = value
    return payload


def _follow_up_questions(
    *,
    intent: dict[str, Any],
    branch: dict[str, Any],
    requires_account: bool,
    strategy: str,
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    if requires_account and strategy == "none":
        questions.append(
            {
                "field": "account",
                "label": "绑定账号",
                "required": True,
                "reason": "app 级 AI 任务需要账号上下文。",
            }
        )
    if branch.get("needs_confirmation") and intent.get("prefers_branch"):
        questions.append(
            {
                "field": "branch_id",
                "label": "确认业务分支",
                "required": False,
                "reason": "当前 goal 没有明确分支词，暂按默认分支规划。",
            }
        )
    if intent.get("expects_keyword_input") and not branch.get("search_keyword_count"):
        questions.append(
            {
                "field": "keyword",
                "label": "搜索关键词",
                "required": False,
                "reason": "当前分支没有可复用关键词池，执行时可能需要人工补充。",
            }
        )
    if intent.get("expects_reply_strategy") and not branch.get("reply_ai_type"):
        questions.append(
            {
                "field": "reply_ai_type",
                "label": "回复策略",
                "required": False,
                "reason": "当前分支未配置回复 AI 类型，将按通用探索策略执行。",
            }
        )
    return questions


def _operator_summary(
    *,
    app_name: str,
    intent: dict[str, Any],
    branch: dict[str, Any],
    strategy: str,
    ready_count: int,
    account_required: bool,
    top_workflow: dict[str, Any],
    has_app_config: bool,
) -> str:
    parts = [f"目标识别为「{intent['label']}」"]
    if app_name:
        parts.append(f"应用上下文是 {app_name}")
    if branch.get("label"):
        parts.append(f"当前按 {branch['label']} 分支规划")
    if strategy == "selected":
        parts.append("将直接使用已选账号")
    elif strategy == "pool":
        parts.append(f"可从账号池领取就绪账号（当前 {ready_count} 个）")
    elif not account_required:
        parts.append("当前任务已声明无需账号数据")
    else:
        parts.append("当前缺少可用账号")
    if top_workflow.get("task") and top_workflow["task"] != "agent_executor":
        parts.append(f"最接近的固定工作流是 {top_workflow['display_name']}")
    elif not has_app_config:
        parts.append("当前更适合先走探索式执行补齐 app 骨架")
    return "，".join(parts) + "。"


def _memory_suggestions(memory: dict[str, Any], intent: dict[str, Any]) -> list[str]:
    if not memory.get("available"):
        return []
    suggestions: list[str] = []
    for item in memory.get("hints") or []:
        text = _collapse_ws(item)
        if text and text not in suggestions:
            suggestions.append(text)
    latest = memory.get("latest")
    if isinstance(latest, dict):
        distill_reason = str(latest.get("distill_reason") or "").strip()
        hint = memory_hint_for_reason(intent, distill_reason)
        if hint:
            suggestions.append(hint)
    return suggestions[:5]


def _execution_next_step(default_step: str, memory: dict[str, Any], intent: dict[str, Any]) -> str:
    if not memory.get("available"):
        return default_step
    latest = memory.get("latest")
    if not isinstance(latest, dict):
        return default_step
    distill_reason = str(latest.get("distill_reason") or "").strip()
    hint = memory_hint_for_reason(intent, distill_reason)
    recommended_action = str(memory.get("recommended_action") or "").strip()
    if recommended_action == "distill_or_validate":
        return "最近已积累可作为蒸馏样本的运行资产；优先继续验证或直接进入蒸馏评估。"
    if recommended_action == "continue_from_memory":
        if hint:
            return hint
        return "最近已有可复用运行资产；优先沿最近终态和已验证入口继续执行。"
    if recommended_action == "reuse_context":
        return "最近已沉淀上下文线索；优先复用已记录条件、页面终态和人工输入，再继续执行。"
    accepted_count = int(memory.get("accepted_count") or 0)
    if hint and str(latest.get("distill_decision") or "").strip() != "accepted":
        return f"最近同类任务未形成新样本；{hint}"
    if accepted_count > 0 and list(memory.get("entry_actions") or []):
        return "最近已有可复用执行资产；优先沿已验证入口继续执行，减少重复探索。"
    if str(latest.get("value_level") or "").strip() in {"replayable", "useful_trace"}:
        return "最近已有可复用运行资产；优先复用最近页面入口与终态信息再继续。"
    return default_step


def _llm_planner_system_prompt() -> str:
    return (
        "你是 WebRPA 的 ai_dialog_planner。"
        "请根据输入生成一个简短 JSON，帮助前端确认 AI 对话任务的展示文案。"
        "只返回 JSON 对象，字段可包含 display_name、operator_summary、missing、suggestions。"
    )


def _llm_planner_prompt(
    *,
    goal: str,
    app_id: str,
    account_required: bool,
    selected_account: str,
    ready_count: int,
    advanced_prompt: str,
    expected_state_ids: list[str],
    intent: dict[str, Any],
    branch: dict[str, Any],
    control_flow: dict[str, Any],
    workflows: list[dict[str, Any]],
) -> str:
    payload = {
        "goal": goal,
        "app_id": app_id,
        "account_required": account_required,
        "selected_account": selected_account or None,
        "ready_account_count": ready_count,
        "advanced_prompt": advanced_prompt or None,
        "expected_state_ids": expected_state_ids,
        "intent": {
            "task_family": intent.get("task_family"),
            "objective": intent.get("objective"),
            "label": intent.get("label"),
            "confidence": intent.get("confidence"),
        },
        "branch": {
            "branch_id": branch.get("branch_id"),
            "label": branch.get("label"),
            "source": branch.get("source"),
        },
        "control_flow": {
            "has_hints": bool(control_flow.get("has_hints")),
            "covered_dimensions": list(control_flow.get("covered_dimensions") or []),
            "missing_dimensions": list(control_flow.get("missing_dimensions") or []),
        },
        "recommended_workflows": [
            {
                "task": item.get("task"),
                "display_name": item.get("display_name"),
                "fit": item.get("fit"),
            }
            for item in workflows[:3]
        ],
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
        account_required: bool = True,
        selected_account: str | None = None,
        use_account_twofa: bool = True,
        advanced_prompt: str | None = None,
    ) -> dict[str, Any]:
        normalized_goal = str(goal or "").strip()
        if not normalized_goal:
            raise ValueError("goal is required")
        advanced_prompt_text = str(advanced_prompt or "").strip()

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
            "advanced_prompt": advanced_prompt_text,
            "_workflow_source": "ai_dialog",
        }
        resolved_payload = resolve_app_payload(resolved_app_id, planner_seed_payload)
        config = self._executor.preview_config(resolved_payload)

        app_config = get_app_config(resolved_app_id)
        app_name = str(
            app_config.get("display_name") or identity.get("display_name") or resolved_app_id
        ).strip()
        all_accounts = list_accounts(app_id=resolved_app_id)
        selected_account_text = str(selected_account or "").strip()
        selected_account_record = _selected_account_record(all_accounts, selected_account_text)
        ready_accounts = _ready_accounts(all_accounts)
        ready_count = len(ready_accounts)
        selected_twofa_secret = (
            str(selected_account_record.get("twofa") or selected_account_record.get("twofa_secret") or "").strip()
            if isinstance(selected_account_record, dict)
            else ""
        )

        intent = infer_intent(normalized_goal, app_id=resolved_app_id)
        control_flow_analysis = analyze_control_flow_prompt(
            normalized_goal,
            advanced_prompt=advanced_prompt_text,
        )
        control_flow = {
            "has_hints": bool(control_flow_analysis.get("has_hints")),
            "items": list(control_flow_analysis.get("items") or []),
            "covered_dimensions": list(control_flow_analysis.get("covered_dimensions") or []),
            "missing_dimensions": list(control_flow_analysis.get("missing_dimensions") or []),
            "wait_hints": list(control_flow_analysis.get("wait_hints") or []),
            "success_hints": list(control_flow_analysis.get("success_hints") or []),
        }
        guidance = dict(control_flow_analysis.get("guidance") or {})
        branch = _branch_snapshot(
            app_id=resolved_app_id,
            goal=normalized_goal,
            selected_account_record=selected_account_record,
        )
        inferred_requires_account = bool(intent.get("requires_account"))
        requires_account = inferred_requires_account and bool(account_required)
        strategy = _account_strategy(selected_account_text, ready_count)
        can_execute = not (requires_account and strategy == "none")
        execution_hint = _account_execution_hint(
            strategy=strategy,
            app_id=resolved_app_id,
            selected_account=selected_account_text,
            ready_count=ready_count,
            requires_account=requires_account,
        )
        auto_totp_supported = resolved_app_id == "x" and "login" in str(intent.get("objective") or "").strip()
        auto_totp_ready = (
            auto_totp_supported
            and bool(account_required)
            and bool(selected_account_text)
            and bool(selected_twofa_secret)
        )
        auto_totp_enabled = auto_totp_ready and bool(use_account_twofa)
        challenge_policy = {
            "auto_totp": {
                "supported": auto_totp_supported,
                "ready": auto_totp_ready,
                "enabled": auto_totp_enabled,
                "selected_by_user": bool(use_account_twofa),
                "selected_account_has_twofa": bool(selected_twofa_secret),
                "summary": (
                    "本次执行会自动使用账号 2FA 密钥生成 6 位验证码。"
                    if auto_totp_enabled
                    else (
                        "当前账号和流程都满足自动 2FA 条件，但本次已由用户手动关闭。"
                        if auto_totp_ready and not use_account_twofa
                        else (
                            "当前流程支持自动 2FA，但所选账号未配置 2FA 密钥。"
                            if auto_totp_supported and selected_account_text and not selected_twofa_secret
                            else (
                                "当前流程支持自动 2FA；绑定含 2FA 密钥的账号后可自动启用。"
                                if auto_totp_supported and not selected_account_text
                                else "当前流程未明确匹配自动 2FA 场景。"
                            )
                        )
                    )
                ),
            },
            "human_takeover": {
                "enabled": True,
                "summary": "图形验证码、滑块验证码、短信码、邮箱码或风险确认当前仍以人工接管为主。",
            },
        }

        resolved_payload = _apply_branch_context(
            resolved_payload=resolved_payload,
            intent=intent,
            branch=branch,
        )
        app_tokens = _resolve_app_tokens(
            app_id=resolved_app_id,
            identity=identity,
            app_config=app_config,
        )
        recommended_workflows = _recommended_workflows(
            app_id=resolved_app_id,
            app_tokens=app_tokens,
            has_app_config=bool(app_config),
            intent=intent,
            branch_id=str(branch.get("branch_id") or ""),
            normalized_goal=_normalized_goal_text(normalized_goal),
        )
        memory = self._workflow_drafts.summarize_recent_run_assets(
            app_id=resolved_app_id,
            objective=str(intent.get("objective") or ""),
            branch_id=str(branch.get("branch_id") or ""),
        )
        reuse_plan = build_memory_reuse_plan(
            latest_value_profile=dict(
                ((memory.get("latest") or {}).get("value_profile") or {})
                if isinstance(memory.get("latest"), dict)
                else {}
            ),
            accepted_count=int(memory.get("accepted_count") or 0),
        )
        top_workflow = recommended_workflows[0] if recommended_workflows else {
            "task": "agent_executor",
            "display_name": "AI 探索执行",
            "fit": "medium",
        }
        top_plugin_workflow = next(
            (
                item
                for item in recommended_workflows
                if str(item.get("task") or "").strip() not in ("", "agent_executor")
            ),
            None,
        )

        missing: list[str] = []
        suggestions: list[str] = []
        blockers: list[str] = []
        if requires_account and strategy == "none":
            missing.append("account")
            blockers.append("missing_account")
            suggestions.append("先绑定账号或补充就绪账号池，再下发 app 级 AI 任务。")
        if not app_config:
            suggestions.append("当前应用缺少共享 app 配置，将以探索模式执行。")
        if intent.get("prefers_branch") and branch.get("needs_confirmation"):
            suggestions.append("当前 goal 没有明确业务分支，暂按默认分支规划。")
        if intent.get("expects_keyword_input") and not branch.get("search_keyword_count"):
            suggestions.append("当前分支没有复用关键词池，执行时可能需要人工提供搜索词。")
        if intent.get("expects_reply_strategy") and not branch.get("reply_ai_type"):
            suggestions.append("当前分支未配置回复 AI 类型，将先走通用探索回复。")
        if intent.get("needs_shared_resource"):
            suggestions.append("该类任务通常依赖博主候选池；若池为空，建议先采集一次博主资源。")
        if top_workflow.get("task") and top_workflow["task"] != "agent_executor":
            suggestions.append(
                f"当前目标与 {top_workflow['display_name']} 接近，执行稳定后可迁移为固定插件。"
            )
        for item in guidance.get("suggestions") or []:
            text = str(item or "").strip()
            if text and text not in suggestions:
                suggestions.append(text)
        for item in _memory_suggestions(memory, intent):
            if item not in suggestions:
                suggestions.append(item)

        questions = _follow_up_questions(
            intent=intent,
            branch=branch,
            requires_account=requires_account,
            strategy=strategy,
        )
        execution = {
            "runtime": "agent_executor",
            "mode": (
                "workflow_aligned"
                if top_plugin_workflow is not None
                else ("exploration_bootstrap" if not app_config else "guided_exploration")
            ),
            "readiness": "ready" if can_execute else "blocked",
            "can_execute": can_execute,
            "blocking_reasons": blockers,
            "next_step": _execution_next_step(
                (
                    "先补充账号，再重新规划。"
                    if blockers
                    else (
                        f"先按 {top_plugin_workflow['display_name']} 的意图执行一次 AI 托管任务。"
                        if top_plugin_workflow is not None
                        else "先执行一次 AI 探索任务，收集可复用路径与配置证据。"
                    )
                ),
                memory,
                intent,
            ),
            "migration_target": (
                top_plugin_workflow.get("task") if top_plugin_workflow is not None else None
            ),
            "memory_ready": bool(memory.get("available")),
            "reuse_priority": reuse_plan["reuse_priority"],
            "reuse_action": reuse_plan["recommended_action"],
            "distill_eligible": reuse_plan["distill_eligible"],
        }

        operator_summary = _operator_summary(
            app_name=app_name,
            intent=intent,
            branch=branch,
            strategy=strategy,
            ready_count=ready_count,
            account_required=account_required,
            top_workflow=top_workflow,
            has_app_config=bool(app_config),
        )
        if memory.get("available"):
            asset_count = int(memory.get("asset_count") or 0)
            operator_summary = f"{operator_summary[:-1]}，且最近已有 {asset_count} 条同类运行资产可复用。"
        llm_plan = self._plan_with_llm(
            goal=normalized_goal,
            app_id=resolved_app_id,
            account_required=bool(account_required),
            selected_account=selected_account_text,
            advanced_prompt=str(advanced_prompt or "").strip(),
            expected_state_ids=list(config.expected_state_ids),
            ready_count=ready_count,
            intent=intent,
            branch=branch,
            control_flow=control_flow,
            workflows=recommended_workflows,
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

        display_name = (
            str(llm_plan.get("display_name") or "").strip()
            or _recommended_title(app_name, intent, normalized_goal, resolved_app_id)
        )
        declarative_scripts = _declarative_scripts_for_workflows(
            app_id=resolved_app_id,
            intent=intent,
            branch=branch,
            workflows=recommended_workflows,
        )
        resolved_payload.update(
            {
                "_planner_objective": str(intent.get("objective") or "").strip(),
                "_planner_control_flow_hints": list(control_flow.get("items") or []),
                "_planner_control_flow_summary": str(guidance.get("summary") or "").strip(),
                "use_account_twofa": bool(use_account_twofa),
                "expected_state_ids": list(config.expected_state_ids),
                "allowed_actions": list(config.allowed_actions),
                "max_steps": int(config.max_steps),
                "stagnant_limit": int(config.stagnant_limit),
                **_planner_declarative_context(declarative_scripts),
            }
        )

        return {
            "display_name": display_name,
            "task": "agent_executor",
            "source": "ai_dialog",
            "operator_summary": operator_summary,
            "resolved_app": {
                "app_id": resolved_app_id,
                "name": app_name,
                "package": str(resolved_payload.get("package") or "").strip() or None,
                "has_app_config": bool(app_config),
                "agent_hint": get_app_agent_hint(resolved_app_id) or None,
            },
            "resolved_payload": resolved_payload,
            "guidance": guidance,
            "follow_up": {
                "missing": missing,
                "suggestions": suggestions,
                "questions": questions,
                "message": (
                    suggestions[0]
                    if suggestions
                    else (questions[0]["reason"] if questions else "")
                ),
            },
            "account": {
                "account_required": bool(account_required),
                "selected_account": selected_account_text or None,
                "selected_account_default_branch": (
                    normalize_branch_id(selected_account_record.get("default_branch"), default="")
                    if isinstance(selected_account_record, dict)
                    else None
                ),
                "ready_count": ready_count,
                "strategy": strategy,
                "execution_hint": execution_hint,
                "intent_requires_account": inferred_requires_account,
                "requires_account": requires_account,
                "can_execute": can_execute,
            },
            "intent": {
                "task_family": intent["task_family"],
                "objective": intent["objective"],
                "label": intent["label"],
                "confidence": intent["confidence"],
                "matched_keywords": list(intent.get("matched_keywords") or []),
                "account_required": bool(account_required),
                "intent_requires_account": inferred_requires_account,
                "requires_account": requires_account,
                "prefers_branch": bool(intent.get("prefers_branch")),
                "needs_shared_resource": bool(intent.get("needs_shared_resource")),
                "expected_outcome": intent.get("expected_outcome"),
                "reason": intent.get("reason"),
            },
            "control_flow": control_flow,
            "branch": branch,
            "execution": execution,
            "memory": memory,
            "challenge_policy": challenge_policy,
            "recommended_workflows": recommended_workflows,
            "declarative_scripts": declarative_scripts,
            "draft": {
                "source": "ai_dialog",
                "display_name_candidate": display_name,
            },
        }

    def list_history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._workflow_drafts.list_ai_dialog_history(limit=limit)

    def _plan_with_llm(
        self,
        *,
        goal: str,
        app_id: str,
        account_required: bool,
        selected_account: str,
        advanced_prompt: str,
        expected_state_ids: list[str],
        ready_count: int,
        intent: dict[str, Any],
        branch: dict[str, Any],
        control_flow: dict[str, Any],
        workflows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        client = self._llm_client_factory()
        request = LLMRequest(
            prompt=_llm_planner_prompt(
                goal=goal,
                app_id=app_id,
                account_required=account_required,
                selected_account=selected_account,
                ready_count=ready_count,
                advanced_prompt=advanced_prompt,
                expected_state_ids=expected_state_ids,
                intent=intent,
                branch=branch,
                control_flow=control_flow,
                workflows=workflows,
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
