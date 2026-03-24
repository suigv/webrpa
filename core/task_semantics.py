from __future__ import annotations

import re
from typing import Any

from engine.models.manifest import (
    PluginAIHints,
    PluginDistillPolicy,
    PluginDistillRule,
    PluginManifest,
)
from engine.plugin_loader import get_shared_plugin_loader

_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")

_EXPLORATION_INTENT = {
    "objective": "exploration",
    "label": "探索执行",
    "task_family": "exploration",
    "requires_account": True,
    "prefers_branch": False,
    "needs_shared_resource": False,
    "expects_keyword_input": False,
    "expects_reply_strategy": False,
    "expected_outcome": "先通过 AI 探索可执行路径，再决定是否沉淀为固定插件。",
    "memory_hints": {},
}

_GENERIC_MEMORY_HINTS = {
    "partial_path_only": "最近执行已跑通部分路径；下次优先复用已验证入口继续补终态。",
    "useful_trace_only": "最近保留了可复用轨迹，可继续沿已有入口缩短探索路径。",
    "failed_run": "最近同类任务失败过，可先根据最近终态修正阻塞点。",
    "cancelled_run": "最近同类任务存在人工中断记录，可复用已到达页面与上下文。",
}


def _collapse_ws(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def normalize_goal_text(value: str) -> str:
    return _NON_WORD_RE.sub(" ", _collapse_ws(value).lower())


def _token_matches(text: str, keywords: list[str]) -> list[str]:
    matched: list[str] = []
    for keyword in keywords:
        token = str(keyword or "").strip().lower()
        if token and token in text and token not in matched:
            matched.append(token)
    return matched


def _manifest_declared_app_id(manifest: PluginManifest) -> str:
    for item in manifest.inputs:
        if item.name == "app_id":
            return str(item.default or "").strip().lower()
    return ""


def _hint_to_dict(hint: PluginAIHints) -> dict[str, Any]:
    return {
        "objective": hint.objective,
        "label": hint.label,
        "task_family": hint.task_family,
        "keywords": list(hint.keywords),
        "plugin_keywords": list(hint.plugin_keywords),
        "requires_account": bool(hint.requires_account),
        "prefers_branch": bool(hint.prefers_branch),
        "needs_shared_resource": bool(hint.needs_shared_resource),
        "expects_keyword_input": bool(hint.expects_keyword_input),
        "expects_reply_strategy": bool(hint.expects_reply_strategy),
        "expected_outcome": hint.expected_outcome,
        "memory_hints": dict(hint.memory_hints or {}),
        "distill_policy": hint.distill_policy,
    }


def exploration_intent() -> dict[str, Any]:
    return dict(_EXPLORATION_INTENT)


def list_manifest_intents() -> list[dict[str, Any]]:
    intents: list[dict[str, Any]] = []
    loader = get_shared_plugin_loader()
    for name in loader.names:
        entry = loader.get(name)
        if entry is None or entry.manifest.ai_hints is None:
            continue
        data = _hint_to_dict(entry.manifest.ai_hints)
        data["plugin_name"] = entry.manifest.name
        data["app_id"] = _manifest_declared_app_id(entry.manifest)
        intents.append(data)
    return intents


def infer_intent(goal: str, *, app_id: str = "") -> dict[str, Any]:
    normalized_goal = normalize_goal_text(goal)
    best_intent: dict[str, Any] | None = None
    best_score = 0
    best_matches: list[str] = []
    for item in list_manifest_intents():
        matches = _token_matches(normalized_goal, list(item.get("keywords") or []))
        if not matches:
            continue
        score = sum(2 if len(token) >= 4 else 1 for token in matches)
        declared_app_id = str(item.get("app_id") or "").strip()
        if app_id and declared_app_id and declared_app_id == app_id:
            score += 2
        elif app_id and declared_app_id and declared_app_id != app_id:
            score -= 2
        if score > best_score:
            best_intent = item
            best_score = score
            best_matches = matches
    if best_intent is None:
        return {
            **exploration_intent(),
            "confidence": "low",
            "matched_keywords": [],
            "reason": "未命中稳定任务语义，先按探索执行处理。",
        }
    return {
        **{key: value for key, value in best_intent.items() if key not in {"plugin_name", "app_id"}},
        "confidence": "high" if best_score >= 4 else "medium",
        "matched_keywords": best_matches,
        "reason": f"命中意图关键词：{', '.join(best_matches[:3])}",
    }


def resolve_intent_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    explicit_objective = str(payload.get("_planner_objective") or "").strip()
    task_name = str(payload.get("task") or "").strip()
    app_id = str(payload.get("app_id") or "").strip()
    loader = get_shared_plugin_loader()
    if task_name:
        entry = loader.get(task_name)
        if entry is not None and entry.manifest.ai_hints is not None:
            return _hint_to_dict(entry.manifest.ai_hints)
    if explicit_objective:
        for item in list_manifest_intents():
            if str(item.get("objective") or "").strip() == explicit_objective:
                declared_app_id = str(item.get("app_id") or "").strip()
                if not app_id or not declared_app_id or declared_app_id == app_id:
                    return {key: value for key, value in item.items() if key not in {"plugin_name", "app_id"}}
        return {
            **exploration_intent(),
            "objective": explicit_objective,
            "label": explicit_objective,
        }
    goal = str(payload.get("goal") or payload.get("prompt") or "").strip()
    if goal:
        return infer_intent(goal, app_id=app_id)
    return exploration_intent()


def policy_data_count(policy: PluginDistillPolicy | None, data: dict[str, Any]) -> tuple[bool, int]:
    keys = list(policy.data_count_keys) if policy is not None else []
    list_keys = list(policy.data_count_list_keys) if policy is not None else []
    observed = False
    for key in keys:
        if key not in data:
            continue
        observed = True
        raw = data.get(key)
        if isinstance(raw, bool):
            continue
        try:
            value = int(raw)
        except Exception:
            continue
        if value > 0:
            return True, value
    for key in list_keys:
        if key not in data:
            continue
        observed = True
        raw = data.get(key)
        if isinstance(raw, list) and raw:
            return True, len(raw)
    return observed, 0


def match_distill_rule(
    policy: PluginDistillPolicy | None,
    *,
    terminal_message: str,
    data_count_present: bool,
    data_count: int,
) -> PluginDistillRule | None:
    if policy is None:
        return None
    lowered = terminal_message.lower()
    for rule in policy.completed_rules:
        if rule.match_message_any and not any(
            str(marker).lower() in lowered for marker in rule.match_message_any
        ):
            continue
        if rule.match_data_count_present and not data_count_present:
            continue
        if rule.match_data_count_positive and data_count <= 0:
            continue
        if rule.match_data_count_zero and (not data_count_present or data_count != 0):
            continue
        if rule.match_terminal_message_present and not terminal_message:
            continue
        if not (
            rule.match_message_any
            or rule.match_data_count_present
            or rule.match_data_count_positive
            or rule.match_data_count_zero
            or rule.match_terminal_message_present
            or rule.match_always
        ):
            continue
        return rule
    return None


def memory_hint_for_reason(intent: dict[str, Any], reason: str) -> str | None:
    custom_hints = intent.get("memory_hints")
    if isinstance(custom_hints, dict):
        text = str(custom_hints.get(reason) or "").strip()
        if text:
            return text
    fallback = _GENERIC_MEMORY_HINTS.get(reason)
    return str(fallback).strip() if fallback else None
