from __future__ import annotations

import random
import re
from collections.abc import Callable
from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext


def pick_weighted_keyword_action(
    params: dict[str, Any],
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    blogger = str(params.get("blogger") or "").strip()
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "keyword": override,
                "rendered_keyword": override,
                "source": "override",
                "ai_type": ai_type,
            },
        )

    try:
        document = load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))

    strategies = document.get("strategies", {})
    strategy = strategies.get(ai_type) or strategies.get("default")
    if not isinstance(strategy, dict):
        return ActionResult(
            ok=False, code="strategy_missing", message=f"strategy not found: {ai_type}"
        )

    keywords = strategy.get("keywords", {})
    weights = strategy.get("weights", {})
    weighted_pool: list[tuple[str, str]] = []
    for bucket_name, entries in keywords.items():
        if not isinstance(entries, list):
            continue
        try:
            weight = int(weights.get(bucket_name, 1))
        except Exception:
            weight = 1
        for entry in entries:
            entry_text = str(entry).strip()
            if not entry_text:
                continue
            weighted_pool.extend([(bucket_name, entry_text)] * max(weight, 1))

    if not weighted_pool:
        return ActionResult(
            ok=False, code="empty_keyword_pool", message=f"keyword pool empty: {ai_type}"
        )

    bucket, keyword = random.choice(weighted_pool)
    rendered = keyword.replace("{blogger}", blogger) if blogger else keyword
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "ai_type": ai_type,
            "bucket": bucket,
            "keyword": keyword,
            "rendered_keyword": rendered,
        },
    )


def is_text_blacklisted_action(
    params: dict[str, Any],
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    text = str(params.get("text") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    try:
        document = load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))
    strategies = document.get("strategies", {})
    strategy = strategies.get(ai_type) or strategies.get("default")
    if not isinstance(strategy, dict):
        return ActionResult(
            ok=False, code="strategy_missing", message=f"strategy not found: {ai_type}"
        )
    blacklist = strategy.get("blacklist", [])
    if not isinstance(blacklist, list):
        blacklist = []
    for word in blacklist:
        word_text = str(word).strip()
        if word_text and word_text in text:
            return ActionResult(
                ok=True,
                code="ok",
                data={"contains": True, "matched": word_text, "ai_type": ai_type},
            )
    return ActionResult(
        ok=True, code="ok", data={"contains": False, "matched": "", "ai_type": ai_type}
    )


def generate_dm_reply_action(
    params: dict[str, Any],
    *,
    select_interaction_template: Callable[[str, str], str],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    last_message = str(params.get("last_message") or "").strip()
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data={"reply_text": override, "source": "override", "ai_type": ai_type},
        )
    try:
        template = select_interaction_template("dm_reply", ai_type)
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_text_unavailable", message=str(exc))
    snippet = re.sub(r"\s+", " ", last_message).strip()
    if snippet:
        snippet = snippet[:24]
        reply_text = f"{template} {snippet}"
    else:
        reply_text = template
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "reply_text": reply_text[:120],
            "source": "template",
            "ai_type": ai_type,
            "last_message": last_message,
        },
    )


def generate_quote_text_action(
    params: dict[str, Any],
    *,
    select_interaction_template: Callable[[str, str], str],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    source_text = str(
        params.get("source_text")
        or params.get("candidate_text")
        or params.get("target_post_url")
        or ""
    ).strip()
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data={"quote_text": override, "source": "override", "ai_type": ai_type},
        )
    try:
        template = select_interaction_template("quote_text", ai_type)
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_text_unavailable", message=str(exc))
    snippet = re.sub(r"\s+", " ", source_text).strip()
    if snippet:
        snippet = snippet[:28]
        quote_text = f"{template} {snippet}"
    else:
        quote_text = template
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "quote_text": quote_text[:140],
            "source": "template",
            "ai_type": ai_type,
            "source_text": source_text,
        },
    )


def save_blogger_candidate_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    append_shared_unique: Callable[[dict[str, Any], ExecutionContext | None], ActionResult],
) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")
    shared_key = params.get("key", params.get("shared_key", "blogger_pool"))
    wrapped_params = {
        "key": shared_key,
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "identity_field": params.get("identity_field", "username"),
        "item": candidate,
    }
    result = append_shared_unique(wrapped_params, context)
    if not result.ok:
        return result
    payload = dict(result.data)
    payload["candidate"] = candidate
    return ActionResult(ok=True, code="ok", data=payload)


def get_blogger_candidate_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    load_shared_optional: Callable[[dict[str, Any], ExecutionContext | None], ActionResult],
) -> ActionResult:
    shared_key = params.get("key", params.get("shared_key", "blogger_pool"))
    wrapped_params = {
        "key": shared_key,
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "default": [],
    }
    result = load_shared_optional(wrapped_params, context)
    if not result.ok:
        return result
    items = result.data.get("value", [])
    if not isinstance(items, list):
        items = []
    index = int(params.get("index", 0) or 0)
    if index < 0 or index >= len(items):
        return ActionResult(
            ok=False,
            code="blogger_candidate_missing",
            message="blogger candidate not found",
            data={"size": len(items), "index": index},
        )
    return ActionResult(
        ok=True, code="ok", data={"candidate": items[index], "index": index, "size": len(items)}
    )


def mark_processed_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    append_shared_unique: Callable[[dict[str, Any], ExecutionContext | None], ActionResult],
) -> ActionResult:
    item = params.get("item")
    if item in (None, ""):
        return ActionResult(ok=False, code="invalid_params", message="item is required")
    wrapped_params = {
        "key": params.get("key", "processed_items"),
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "item": item,
    }
    result = append_shared_unique(wrapped_params, context)
    if not result.ok:
        return result
    payload = dict(result.data)
    payload["item"] = item
    return ActionResult(ok=True, code="ok", data=payload)


def check_processed_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    load_shared_optional: Callable[[dict[str, Any], ExecutionContext | None], ActionResult],
) -> ActionResult:
    item = params.get("item")
    if item in (None, ""):
        return ActionResult(ok=False, code="invalid_params", message="item is required")
    wrapped_params = {
        "key": params.get("key", "processed_items"),
        "scope": params.get("scope", "device"),
        "scope_value": params.get("scope_value"),
        "default": [],
    }
    result = load_shared_optional(wrapped_params, context)
    if not result.ok:
        return result
    items = result.data.get("value", [])
    if not isinstance(items, list):
        items = []
    contains = item in items
    return ActionResult(
        ok=True, code="ok", data={"contains": contains, "item": item, "size": len(items)}
    )


def pick_candidate_action(
    params: dict[str, Any],
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    candidates = params.get("candidates")
    if not isinstance(candidates, list):
        return ActionResult(ok=False, code="invalid_params", message="candidates must be a list")

    ai_type = str(params.get("ai_type") or "default").strip()
    strategy = str(params.get("strategy") or "best").strip().lower()
    min_text_length = int(params.get("min_text_length", 4) or 4)

    try:
        document = load_strategy_document()
        strategies = document.get("strategies", {})
        strategy_cfg = strategies.get(ai_type) or strategies.get("default") or {}
        blacklist = strategy_cfg.get("blacklist", []) if isinstance(strategy_cfg, dict) else []
        scoring_cfg = (
            strategy_cfg.get("candidate_scoring", {}) if isinstance(strategy_cfg, dict) else {}
        )
    except Exception:
        blacklist = []
        scoring_cfg = {}

    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        text = str(candidate.get("text") or "").strip()
        desc = str(candidate.get("desc") or "").strip()
        combined = " ".join(part for part in (text, desc) if part).strip()
        if len(combined) < min_text_length:
            continue
        if any(str(word).strip() and str(word).strip() in combined for word in blacklist):
            continue

        score = 1
        if candidate.get("has_media"):
            score += 3 + scoring_cfg.get("has_media_bonus", 0)
        for bonus in scoring_cfg.get("keyword_bonuses", []):
            kw = str(bonus.get("text") or "").strip()
            if not kw:
                continue
            target = combined.lower() if bonus.get("case_insensitive") else combined
            needle = kw.lower() if bonus.get("case_insensitive") else kw
            if needle in target:
                score += int(bonus.get("score", 0))
        score += min(len(combined), 120) // 20
        scored.append((score, candidate))

    if not scored:
        return ActionResult(ok=False, code="no_candidate_selected", message="no candidate selected")

    if strategy == "random":
        _, selected = random.choice(scored)
    elif strategy == "first":
        _, selected = scored[0]
    else:
        selected = max(scored, key=lambda item: item[0])[1]
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "candidate": selected,
            "count": len(scored),
            "ai_type": ai_type,
            "strategy": strategy,
        },
    )


def choose_blogger_search_query_action(
    params: dict[str, Any],
    *,
    load_interaction_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    ai_type = str(params.get("ai_type") or "default").strip()
    if override:
        return ActionResult(
            ok=True, code="ok", data={"query": override, "source": "override", "ai_type": ai_type}
        )
    try:
        document = load_interaction_document()
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_config_unavailable", message=str(exc))
    search_query_cfg = document.get("search_query", {})
    candidates = search_query_cfg.get(ai_type) or search_query_cfg.get("default") or []
    if not candidates:
        return ActionResult(
            ok=False,
            code="search_query_missing",
            message=f"no search_query configured for: {ai_type}",
        )
    query = random.choice(candidates)
    return ActionResult(
        ok=True, code="ok", data={"query": query, "source": "config", "ai_type": ai_type}
    )


def derive_blogger_profile_action(
    params: dict[str, Any],
    *,
    derive_blogger_profile_data: Callable[..., dict[str, Any] | None],
) -> ActionResult:
    candidate = params.get("candidate")
    if not isinstance(candidate, dict):
        return ActionResult(ok=False, code="invalid_params", message="candidate must be an object")

    profile = derive_blogger_profile_data(
        candidate=candidate,
        fallback_username=str(params.get("fallback_username") or "").strip(),
        fallback_display_name=str(params.get("fallback_display_name") or "").strip(),
        fallback_profile=str(params.get("fallback_profile") or "").strip(),
    )
    if profile is None:
        return ActionResult(
            ok=False, code="blogger_profile_missing", message="unable to derive blogger identity"
        )

    return ActionResult(ok=True, code="ok", data=profile)


def save_blogger_candidates_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    derive_blogger_profile_data: Callable[..., dict[str, Any] | None],
    save_blogger_candidate: Callable[[dict[str, Any], ExecutionContext | None], ActionResult],
) -> ActionResult:
    candidates = params.get("candidates")
    if not isinstance(candidates, list):
        return ActionResult(ok=False, code="invalid_params", message="candidates must be a list")

    key = params.get("key", "blogger_pool")
    scope = params.get("scope", "device")
    scope_value = params.get("scope_value")
    identity_field = str(params.get("identity_field") or "username").strip() or "username"
    fallback_profile = str(params.get("fallback_profile") or "").strip()

    added_items: list[dict[str, Any]] = []
    skipped_count = 0
    last_result: ActionResult | None = None

    for candidate in candidates:
        if not isinstance(candidate, dict):
            skipped_count += 1
            continue
        derived = derive_blogger_profile_data(
            candidate=candidate, fallback_profile=fallback_profile
        )
        if derived is None or not str(derived.get(identity_field) or "").strip():
            skipped_count += 1
            continue
        result = save_blogger_candidate(
            {
                "key": key,
                "scope": scope,
                "scope_value": scope_value,
                "identity_field": identity_field,
                "candidate": derived,
            },
            context,
        )
        if not result.ok:
            return result
        last_result = result
        if result.data.get("added") is True:
            added_items.append(derived)

    if last_result is None:
        return ActionResult(
            ok=False,
            code="blogger_candidates_missing",
            message="no blogger candidates saved",
            data={"added_count": 0, "skipped_count": skipped_count, "candidates": []},
        )

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": last_result.data.get("key"),
            "size": last_result.data.get("size", 0),
            "added_count": len(added_items),
            "skipped_count": skipped_count,
            "candidates": added_items,
        },
    )
