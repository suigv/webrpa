from __future__ import annotations

import random
import re
from collections.abc import Callable
from typing import Any

from core.business_profile import branch_id_from_payload, normalize_branch_id
from core.shared_resource_store import get_shared_resource_store
from engine.models.runtime import ActionResult, ExecutionContext


def _resolve_branch_id(params: dict[str, Any], context: ExecutionContext | None = None) -> str:
    payload = context.payload if context is not None and isinstance(context.payload, dict) else {}
    raw = (
        params.get("branch_id")
        or params.get("ai_type")
        or payload.get("branch_id")
        or branch_id_from_payload(payload)
    )
    return normalize_branch_id(raw)


def _with_branch_metadata(data: dict[str, Any], branch_id: str) -> dict[str, Any]:
    return {
        **data,
        "branch_id": branch_id,
        "ai_type": branch_id,
    }


def _resource_namespace(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    shared_key: str,
) -> str:
    payload = context.payload if context is not None and isinstance(context.payload, dict) else {}
    app_id = str(payload.get("app_id") or payload.get("app") or "default").strip().lower() or "default"
    branch_id = _resolve_branch_id(params, context)
    explicit = str(
        params.get("resource_namespace")
        or payload.get("resource_namespace")
        or payload.get("_workflow_draft_id")
        or ""
    ).strip()
    scope = explicit or f"{app_id}:{branch_id}"
    return f"{scope}:{shared_key}"


def pick_weighted_keyword_action(
    params: dict[str, Any],
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    branch_id = _resolve_branch_id(params)
    blogger = str(params.get("blogger") or "").strip()
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata(
                {
                "keyword": override,
                "rendered_keyword": override,
                "source": "override",
                },
                branch_id,
            ),
        )

    try:
        document = load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))

    strategies = document.get("strategies", {})
    strategy = strategies.get(branch_id) or strategies.get("default")
    if not isinstance(strategy, dict):
        return ActionResult(
            ok=False, code="strategy_missing", message=f"strategy not found: {branch_id}"
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
            ok=False, code="empty_keyword_pool", message=f"keyword pool empty: {branch_id}"
        )

    bucket, keyword = random.choice(weighted_pool)
    rendered = keyword.replace("{blogger}", blogger) if blogger else keyword
    return ActionResult(
        ok=True,
        code="ok",
        data=_with_branch_metadata(
            {
            "bucket": bucket,
            "keyword": keyword,
            "rendered_keyword": rendered,
            },
            branch_id,
        ),
    )


def is_text_blacklisted_action(
    params: dict[str, Any],
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    text = str(params.get("text") or "").strip()
    branch_id = _resolve_branch_id(params)
    try:
        document = load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))
    strategies = document.get("strategies", {})
    strategy = strategies.get(branch_id) or strategies.get("default")
    if not isinstance(strategy, dict):
        return ActionResult(
            ok=False, code="strategy_missing", message=f"strategy not found: {branch_id}"
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
                data=_with_branch_metadata({"contains": True, "matched": word_text}, branch_id),
            )
    return ActionResult(
        ok=True,
        code="ok",
        data=_with_branch_metadata({"contains": False, "matched": ""}, branch_id),
    )


def generate_dm_reply_action(
    params: dict[str, Any],
    *,
    select_interaction_template: Callable[[str, str], str],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    branch_id = _resolve_branch_id(params)
    last_message = str(params.get("last_message") or "").strip()
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata({"reply_text": override, "source": "override"}, branch_id),
        )
    try:
        template = select_interaction_template("dm_reply", branch_id)
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
        data=_with_branch_metadata(
            {
            "reply_text": reply_text[:120],
            "source": "template",
            "last_message": last_message,
            },
            branch_id,
        ),
    )


def generate_quote_text_action(
    params: dict[str, Any],
    *,
    select_interaction_template: Callable[[str, str], str],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    branch_id = _resolve_branch_id(params)
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
            data=_with_branch_metadata({"quote_text": override, "source": "override"}, branch_id),
        )
    try:
        template = select_interaction_template("quote_text", branch_id)
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
        data=_with_branch_metadata(
            {
            "quote_text": quote_text[:140],
            "source": "template",
            "source_text": source_text,
            },
            branch_id,
        ),
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
    shared_key = str(params.get("key", params.get("shared_key", "blogger_pool"))).strip()
    identity_field = str(params.get("identity_field") or "username").strip() or "username"
    if context is None:
        result = append_shared_unique(
            {
                "key": shared_key,
                "scope": params.get("scope", "device"),
                "scope_value": params.get("scope_value"),
                "identity_field": identity_field,
                "item": candidate,
            },
            context,
        )
        if not result.ok:
            return result
        payload = dict(result.data)
        payload["candidate"] = candidate
        return ActionResult(ok=True, code="ok", data=payload)
    namespace = _resource_namespace(params, context, shared_key=shared_key)
    stats = get_shared_resource_store().collect_items(
        namespace=namespace,
        items=[candidate],
        identity_field=identity_field,
    )
    data = {
        "key": shared_key,
        "namespace": namespace,
        "candidate": candidate,
        "added": stats["added"] > 0,
    }
    data.update(get_shared_resource_store().namespace_stats(namespace))
    return ActionResult(ok=True, code="ok", data=data)


def get_blogger_candidate_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    load_shared_optional: Callable[[dict[str, Any], ExecutionContext | None], ActionResult],
) -> ActionResult:
    shared_key = str(params.get("key", params.get("shared_key", "blogger_pool"))).strip()
    namespace = _resource_namespace(params, context, shared_key=shared_key)
    owner_id = str(getattr(context, "task_id", "") or "").strip()
    if not owner_id and context is not None:
        owner_id = str(context.runtime.get("task_id") or "").strip()
    if not owner_id:
        result = load_shared_optional(
            {
                "key": shared_key,
                "scope": params.get("scope", "device"),
                "scope_value": params.get("scope_value"),
                "default": [],
            },
            context,
        )
        if not result.ok:
            return result
        items = result.data.get("value", [])
        if not isinstance(items, list) or not items:
            return ActionResult(
                ok=False,
                code="blogger_candidate_missing",
                message="blogger candidate not found",
                data={"namespace": namespace},
            )
        return ActionResult(ok=True, code="ok", data={"candidate": items[0], "namespace": namespace})
    claimed = get_shared_resource_store().claim_next(namespace=namespace, owner_id=owner_id)
    if claimed is None:
        stats = get_shared_resource_store().namespace_stats(namespace)
        return ActionResult(
            ok=False,
            code="blogger_candidate_missing",
            message="blogger candidate not found",
            data={"namespace": namespace, **stats},
        )
    stats = get_shared_resource_store().namespace_stats(namespace)
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "candidate": claimed.item,
            "namespace": namespace,
            "item_id": claimed.item_id,
            "claim_state": claimed.state,
            **stats,
        },
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

    branch_id = _resolve_branch_id(params)
    strategy = str(params.get("strategy") or "best").strip().lower()
    min_text_length = int(params.get("min_text_length", 4) or 4)

    try:
        document = load_strategy_document()
        strategies = document.get("strategies", {})
        strategy_cfg = strategies.get(branch_id) or strategies.get("default") or {}
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
            **_with_branch_metadata({}, branch_id),
            "strategy": strategy,
        },
    )


def choose_blogger_search_query_action(
    params: dict[str, Any],
    *,
    load_interaction_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    branch_id = _resolve_branch_id(params)
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata({"query": override, "source": "override"}, branch_id),
        )
    try:
        document = load_interaction_document()
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_config_unavailable", message=str(exc))
    search_query_cfg = document.get("search_query", {})
    candidates = search_query_cfg.get(branch_id) or search_query_cfg.get("default") or []
    if not candidates:
        return ActionResult(
            ok=False,
            code="search_query_missing",
            message=f"no search_query configured for: {branch_id}",
        )
    query = random.choice(candidates)
    return ActionResult(
        ok=True,
        code="ok",
        data=_with_branch_metadata({"query": query, "source": "config"}, branch_id),
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

    key = str(params.get("key", "blogger_pool")).strip()
    identity_field = str(params.get("identity_field") or "username").strip() or "username"
    fallback_profile = str(params.get("fallback_profile") or "").strip()
    namespace = _resource_namespace(params, context, shared_key=key)

    added_items: list[dict[str, Any]] = []
    skipped_count = 0

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
                "identity_field": identity_field,
                "candidate": derived,
                "resource_namespace": namespace,
            },
            context,
        )
        if not result.ok:
            return result
        if result.data.get("added") is True:
            added_items.append(derived)

    if not candidates:
        return ActionResult(
            ok=False,
            code="blogger_candidates_missing",
            message="no blogger candidates saved",
            data={"added_count": 0, "skipped_count": skipped_count, "candidates": []},
        )

    stats = get_shared_resource_store().namespace_stats(namespace)

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": key,
            "namespace": namespace,
            "added_count": len(added_items),
            "skipped_count": skipped_count,
            "candidates": added_items,
            **stats,
        },
    )
