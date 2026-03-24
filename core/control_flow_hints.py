from __future__ import annotations

import re
from typing import Any

_WS_RE = re.compile(r"\s+")
_CLAUSE_SPLIT_RE = re.compile(r"[；;。！？?!\n]+")

_DIMENSION_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("branch", "条件判断", re.compile(r"(如果|若|否则|一旦|\bif\b|\bwhen\b|\belse\b)", re.IGNORECASE)),
    ("wait", "等待条件", re.compile(r"(等待|直到|等到|出现后|加载后|可见后|\bwait\b|\buntil\b)", re.IGNORECASE)),
    ("timeout", "超时/重试", re.compile(r"(超时|重试|最多|限时|\btimeout\b|\bretry\b)", re.IGNORECASE)),
    ("success", "成功标准", re.compile(r"(算成功|算完成|视为成功|视为完成|成功标准|完成标准|成功后|成功页|\bsuccess\b)", re.IGNORECASE)),
    ("fallback", "失败处理", re.compile(r"(停止|跳过|人工接管|返回失败|报错|中止|\babort\b|\bskip\b|\bfail\b)", re.IGNORECASE)),
)

_CORE_DIMENSIONS = ("branch", "wait", "success")
_DIMENSION_HINTS = {
    "branch": "补一句“如果出现某种页面或异常，就执行什么动作”。",
    "wait": "补一句“等待哪个页面、元素或状态出现后再继续”。",
    "timeout": "如果存在等待，最好补一句“超时多久后怎么处理”。",
    "success": "补一句“看到什么界面、元素或结果就算任务完成”。",
    "fallback": "如果存在分支判断，最好补一句“异常时停止、跳过还是人工接管”。",
}
_DIMENSION_LABELS = {item[0]: item[1] for item in _DIMENSION_RULES}
_GUIDANCE_TIPS = [
    "尽量把描述写成“如果发生什么 -> 怎么处理”。",
    "等待类任务最好写清等待目标和超时处理。",
    "最后补一句“看到什么算成功”，蒸馏更容易收敛成稳定脚本。",
]
_GUIDANCE_EXAMPLE = (
    "例如：如果已经登录就直接结束；如果出现验证码则停止并提示人工接管；"
    "等待首页出现，15 秒内未出现则返回失败；看到首页推荐流算成功。"
)


def _collapse_ws(value: str) -> str:
    return _WS_RE.sub(" ", str(value or "").strip())


def _split_clauses(*parts: str) -> list[str]:
    clauses: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for raw_clause in _CLAUSE_SPLIT_RE.split(str(part or "")):
            clause = _collapse_ws(raw_clause)
            normalized = clause.lower()
            if not clause or normalized in seen:
                continue
            seen.add(normalized)
            clauses.append(clause)
    return clauses


def _item_texts(items: list[dict[str, str]], kind: str) -> list[str]:
    return [str(item.get("text") or "").strip() for item in items if item.get("type") == kind]


def analyze_control_flow_prompt(goal: str, advanced_prompt: str = "") -> dict[str, Any]:
    clauses = _split_clauses(goal, advanced_prompt)
    items: list[dict[str, str]] = []
    seen_items: set[tuple[str, str]] = set()
    covered_dimensions: list[str] = []

    for clause in clauses:
        for dimension, label, pattern in _DIMENSION_RULES:
            if not pattern.search(clause):
                continue
            if dimension not in covered_dimensions:
                covered_dimensions.append(dimension)
            item_key = (dimension, clause)
            if item_key in seen_items:
                continue
            seen_items.add(item_key)
            items.append({"type": dimension, "label": label, "text": clause})

    missing_dimensions = [item for item in _CORE_DIMENSIONS if item not in covered_dimensions]
    if "wait" in covered_dimensions and "timeout" not in covered_dimensions:
        missing_dimensions.append("timeout")
    if "branch" in covered_dimensions and "fallback" not in covered_dimensions:
        missing_dimensions.append("fallback")

    missing_labels = [_DIMENSION_LABELS[item] for item in missing_dimensions if item in _DIMENSION_LABELS]
    suggestions = [
        _DIMENSION_HINTS[item]
        for item in missing_dimensions
        if item in _DIMENSION_HINTS
    ][:3]

    if not items:
        summary = "当前描述还没有明显的条件判断、等待条件或成功标准，蒸馏时更容易只得到线性步骤。"
    elif missing_labels:
        summary = f"已识别 {len(items)} 条控制流提示，还可以补充：{'、'.join(missing_labels)}。"
    else:
        summary = f"已识别 {len(items)} 条控制流提示，已经覆盖条件判断、等待条件和成功标准。"

    return {
        "has_hints": bool(items),
        "items": items[:8],
        "covered_dimensions": covered_dimensions,
        "missing_dimensions": missing_dimensions,
        "wait_hints": _item_texts(items, "wait"),
        "success_hints": _item_texts(items, "success"),
        "guidance": {
            "title": "蒸馏写法建议",
            "summary": summary,
            "tips": list(_GUIDANCE_TIPS),
            "suggestions": suggestions,
            "example": _GUIDANCE_EXAMPLE,
        },
    }
