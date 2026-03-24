from __future__ import annotations

import random
import re
from collections.abc import Callable
from typing import Any

from core.app_branch_service import AppBranchProfileService
from core.business_profile import (
    branch_id_from_payload,
    normalize_branch_id,
    raw_branch_value_from_payload,
)
from core.shared_resource_store import get_shared_resource_store
from engine.models.runtime import ActionResult, ExecutionContext


def _context_payload(context: ExecutionContext | None) -> dict[str, Any]:
    if context is None or not isinstance(context.payload, dict):
        return {}
    return context.payload


def _resolve_app_id(params: dict[str, Any], context: ExecutionContext | None = None) -> str:
    payload = _context_payload(context)
    return (
        str(params.get("app_id") or payload.get("app_id") or payload.get("app") or "default")
        .strip()
        .lower()
        or "default"
    )


def _explicit_branch_raw(params: dict[str, Any], context: ExecutionContext | None = None) -> str:
    payload_branch = raw_branch_value_from_payload(_context_payload(context))
    return str(params.get("branch_id") or params.get("ai_type") or payload_branch or "").strip()


def _resolve_branch_context(
    params: dict[str, Any],
    context: ExecutionContext | None = None,
) -> tuple[str, str, dict[str, Any]]:
    app_id = _resolve_app_id(params, context)
    payload = _context_payload(context)
    explicit_branch = _explicit_branch_raw(params, context)
    fallback_branch = branch_id_from_payload(payload) if payload else "default"
    try:
        branch_bundle = AppBranchProfileService().get_profiles(app_id)
    except Exception:
        branch_id = normalize_branch_id(explicit_branch or fallback_branch)
        return app_id, branch_id, {}
    default_branch = str(branch_bundle.get("default_branch") or "").strip() or fallback_branch
    branch_id = normalize_branch_id(explicit_branch or default_branch, default=default_branch)
    for item in branch_bundle.get("branches") or []:
        if not isinstance(item, dict):
            continue
        if normalize_branch_id(item.get("branch_id"), default="") == branch_id:
            return app_id, branch_id, dict(item)
    return app_id, branch_id, {}


def _list_from_profile(profile: dict[str, Any], key: str) -> list[str]:
    raw = profile.get(key)
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _with_branch_metadata(data: dict[str, Any], branch_id: str) -> dict[str, Any]:
    return {
        **data,
        "branch_id": branch_id,
    }


def _resolve_strategy_config(
    document: dict[str, Any], branch_id: str
) -> dict[str, Any] | None:
    strategies = document.get("strategies", {})
    strategy = strategies.get(branch_id) or strategies.get("default")
    if not isinstance(strategy, dict):
        return None
    return strategy


def _pick_profile_or_legacy_template(
    profile: dict[str, Any],
    *,
    profile_key: str,
    legacy_section: str,
    branch_id: str,
    select_interaction_template: Callable[[str, str], str],
) -> tuple[str, str]:
    profile_templates = _list_from_profile(profile, profile_key)
    if profile_templates:
        return random.choice(profile_templates), "branch_profile"
    return select_interaction_template(legacy_section, branch_id), "legacy_config"


def _render_template_text(template: str, source_text: str, *, snippet_limit: int) -> str:
    snippet = re.sub(r"\s+", " ", source_text).strip()
    if not snippet:
        return template
    return f"{template} {snippet[:snippet_limit]}"


def _resource_namespace(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    shared_key: str,
) -> str:
    payload = _context_payload(context)
    app_id, branch_id, profile = _resolve_branch_context(params, context)
    explicit = str(
        params.get("resource_namespace")
        or payload.get("resource_namespace")
        or payload.get("_workflow_draft_id")
        or profile.get("resource_namespace")
        or ""
    ).strip()
    scope = explicit or f"{app_id}:{branch_id}"
    return f"{scope}:{shared_key}"


def pick_weighted_keyword_action(
    params: dict[str, Any],
    context: ExecutionContext | None = None,
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    _app_id, branch_id, profile = _resolve_branch_context(params, context)
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
    search_keywords = _list_from_profile(profile, "search_keywords")
    if search_keywords:
        keyword = random.choice(search_keywords)
        rendered = keyword.replace("{blogger}", blogger) if blogger else keyword
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata(
                {
                    "bucket": "branch_profile",
                    "keyword": keyword,
                    "rendered_keyword": rendered,
                    "source": "branch_profile",
                },
                branch_id,
            ),
        )

    try:
        document = load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))

    strategy = _resolve_strategy_config(document, branch_id)
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
    context: ExecutionContext | None = None,
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    text = str(params.get("text") or "").strip()
    _app_id, branch_id, profile = _resolve_branch_context(params, context)
    profile_blacklist = _list_from_profile(profile, "blacklist_keywords")
    for word_text in profile_blacklist:
        if word_text in text:
            return ActionResult(
                ok=True,
                code="ok",
                data=_with_branch_metadata(
                    {"contains": True, "matched": word_text, "source": "branch_profile"},
                    branch_id,
                ),
            )
    try:
        document = load_strategy_document()
    except Exception as exc:
        return ActionResult(ok=False, code="strategy_config_unavailable", message=str(exc))
    strategy = _resolve_strategy_config(document, branch_id)
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
    context: ExecutionContext | None = None,
    *,
    select_interaction_template: Callable[[str, str], str],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    payload = _context_payload(context)
    _app_id, branch_id, profile = _resolve_branch_context(params, context)
    last_message = str(params.get("last_message") or "").strip()
    reply_ai_type = str(
        params.get("reply_ai_type")
        or payload.get("reply_ai_type")
        or profile.get("reply_ai_type")
        or ""
    ).strip()
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata(
                {
                    "reply_text": override,
                    "source": "override",
                    "reply_ai_type": reply_ai_type or None,
                },
                branch_id,
            ),
        )
    try:
        template, source = _pick_profile_or_legacy_template(
            profile,
            profile_key="reply_texts",
            legacy_section="dm_reply",
            branch_id=branch_id,
            select_interaction_template=select_interaction_template,
        )
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_text_unavailable", message=str(exc))
    reply_text = _render_template_text(template, last_message, snippet_limit=24)
    return ActionResult(
        ok=True,
        code="ok",
        data=_with_branch_metadata(
            {
                "reply_text": reply_text[:120],
                "source": source,
                "last_message": last_message,
                "reply_ai_type": reply_ai_type or None,
            },
            branch_id,
        ),
    )


def generate_quote_text_action(
    params: dict[str, Any],
    context: ExecutionContext | None = None,
    *,
    select_interaction_template: Callable[[str, str], str],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    _app_id, branch_id, profile = _resolve_branch_context(params, context)
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
        template, source = _pick_profile_or_legacy_template(
            profile,
            profile_key="reply_texts",
            legacy_section="quote_text",
            branch_id=branch_id,
            select_interaction_template=select_interaction_template,
        )
    except Exception as exc:
        return ActionResult(ok=False, code="interaction_text_unavailable", message=str(exc))
    quote_text = _render_template_text(template, source_text, snippet_limit=28)
    return ActionResult(
        ok=True,
        code="ok",
        data=_with_branch_metadata(
            {
                "quote_text": quote_text[:140],
                "source": source,
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
    key = str(params.get("key", "processed_items")).strip() or "processed_items"
    wrapped_params = {"key": key, "item": item}
    if context is None:
        wrapped_params["scope"] = params.get("scope", "device")
        wrapped_params["scope_value"] = params.get("scope_value")
    else:
        wrapped_params["key"] = _resource_namespace(params, context, shared_key=key)
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
    key = str(params.get("key", "processed_items")).strip() or "processed_items"
    wrapped_params = {"key": key, "default": []}
    if context is None:
        wrapped_params["scope"] = params.get("scope", "device")
        wrapped_params["scope_value"] = params.get("scope_value")
    else:
        wrapped_params["key"] = _resource_namespace(params, context, shared_key=key)
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
    context: ExecutionContext | None = None,
    *,
    load_strategy_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    candidates = params.get("candidates")
    if not isinstance(candidates, list):
        return ActionResult(ok=False, code="invalid_params", message="candidates must be a list")

    _app_id, branch_id, profile = _resolve_branch_context(params, context)
    strategy = str(params.get("strategy") or "best").strip().lower()
    min_text_length = int(params.get("min_text_length", 4) or 4)
    blacklist = _list_from_profile(profile, "blacklist_keywords")
    scoring_cfg: dict[str, Any] = {}

    if not blacklist:
        try:
            document = load_strategy_document()
            strategy_cfg = _resolve_strategy_config(document, branch_id) or {}
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
    context: ExecutionContext | None = None,
    *,
    load_interaction_document: Callable[[], dict[str, Any]],
) -> ActionResult:
    override = str(params.get("override") or "").strip()
    _app_id, branch_id, profile = _resolve_branch_context(params, context)
    if override:
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata({"query": override, "source": "override"}, branch_id),
        )
    search_keywords = _list_from_profile(profile, "search_keywords")
    if search_keywords:
        query = random.choice(search_keywords)
        return ActionResult(
            ok=True,
            code="ok",
            data=_with_branch_metadata({"query": query, "source": "branch_profile"}, branch_id),
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
        data=_with_branch_metadata({"query": query, "source": "legacy_config"}, branch_id),
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
