from __future__ import annotations

from typing import Any

from core.app_config import AppConfigManager, get_app_config
from core.business_profile import DEFAULT_BRANCH_ID, branch_label, normalize_branch_id


def _dedupe_texts(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_items = values.replace("\r", "\n").split("\n")
    elif isinstance(values, list):
        raw_items = values
    else:
        raw_items = []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
    return result


def _merge_texts(*groups: Any) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in _dedupe_texts(group):
            if item not in merged:
                merged.append(item)
    return merged


def _clean_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _non_empty_payload_defaults(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        if not name or item in (None, "", [], {}):
            continue
        result[name] = item
    return result


class AppBranchProfileService:
    def get_profiles(self, app_id: str) -> dict[str, Any]:
        normalized_app_id = str(app_id or "").strip().lower()
        if not normalized_app_id:
            raise ValueError("app_id is required")
        config = get_app_config(normalized_app_id)
        branches_doc = _clean_mapping(config.get("branches"))
        legacy_keywords = _clean_mapping(config.get("nurture_keywords"))
        legacy_quotes = _clean_mapping(config.get("quote_texts"))

        branch_ids: list[str] = []
        for raw_key in (
            config.get("default_branch"),
            *branches_doc.keys(),
            *legacy_keywords.keys(),
            *legacy_quotes.keys(),
        ):
            branch_id = normalize_branch_id(raw_key, default="")
            if branch_id and branch_id not in branch_ids:
                branch_ids.append(branch_id)
        if DEFAULT_BRANCH_ID not in branch_ids:
            branch_ids.insert(0, DEFAULT_BRANCH_ID)

        default_branch = normalize_branch_id(
            config.get("default_branch"),
            default=branch_ids[0] if branch_ids else DEFAULT_BRANCH_ID,
        )
        profiles: list[dict[str, Any]] = []
        for branch_id in branch_ids:
            branch_cfg = _clean_mapping(branches_doc.get(branch_id))
            legacy_keyword_cfg = _clean_mapping(legacy_keywords.get(branch_id))
            search_keywords = _merge_texts(
                branch_cfg.get("search_keywords"),
                legacy_keyword_cfg.get("core"),
                legacy_keyword_cfg.get("action"),
                legacy_keyword_cfg.get("derivative"),
                legacy_keyword_cfg.get("target"),
            )
            blacklist_keywords = _merge_texts(
                branch_cfg.get("blacklist_keywords"),
                legacy_keyword_cfg.get("blacklist"),
            )
            reply_texts = _merge_texts(
                branch_cfg.get("reply_texts"),
                legacy_quotes.get(branch_id),
            )
            profiles.append(
                {
                    "branch_id": branch_id,
                    "label": str(branch_cfg.get("label") or branch_label(branch_id)).strip(),
                    "search_keywords": search_keywords,
                    "blacklist_keywords": blacklist_keywords,
                    "reply_texts": reply_texts,
                    "resource_namespace": str(branch_cfg.get("resource_namespace") or "").strip(),
                    "reply_ai_type": str(branch_cfg.get("reply_ai_type") or "").strip(),
                    "payload_defaults": _non_empty_payload_defaults(
                        branch_cfg.get("payload_defaults")
                    ),
                    "notes": str(branch_cfg.get("notes") or "").strip(),
                    "is_default": branch_id == default_branch,
                }
            )

        return {
            "app_id": normalized_app_id,
            "display_name": str(
                config.get("display_name") or config.get("name") or normalized_app_id.upper()
            ).strip(),
            "default_branch": default_branch,
            "branches": profiles,
        }

    def save_profiles(
        self,
        app_id: str,
        *,
        default_branch: str | None,
        branches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        identity = AppConfigManager.ensure_app_config(app_id=app_id)
        normalized_app_id = str(identity["app_id"]).strip()
        document = get_app_config(normalized_app_id) or {"version": "v1"}

        branch_map: dict[str, dict[str, Any]] = {}
        legacy_keywords: dict[str, dict[str, list[str]]] = {}
        legacy_quotes: dict[str, list[str]] = {}

        for raw_item in branches:
            if not isinstance(raw_item, dict):
                continue
            branch_id = normalize_branch_id(raw_item.get("branch_id"), default="")
            if not branch_id:
                continue
            search_keywords = _dedupe_texts(raw_item.get("search_keywords"))
            blacklist_keywords = _dedupe_texts(raw_item.get("blacklist_keywords"))
            reply_texts = _dedupe_texts(raw_item.get("reply_texts"))
            payload_defaults = _non_empty_payload_defaults(raw_item.get("payload_defaults"))
            branch_doc: dict[str, Any] = {}
            label = str(raw_item.get("label") or "").strip()
            if label:
                branch_doc["label"] = label
            if search_keywords:
                branch_doc["search_keywords"] = search_keywords
            if blacklist_keywords:
                branch_doc["blacklist_keywords"] = blacklist_keywords
            if reply_texts:
                branch_doc["reply_texts"] = reply_texts
            resource_namespace = str(raw_item.get("resource_namespace") or "").strip()
            if resource_namespace:
                branch_doc["resource_namespace"] = resource_namespace
            reply_ai_type = str(raw_item.get("reply_ai_type") or "").strip()
            if reply_ai_type:
                branch_doc["reply_ai_type"] = reply_ai_type
            if payload_defaults:
                branch_doc["payload_defaults"] = payload_defaults
            notes = str(raw_item.get("notes") or "").strip()
            if notes:
                branch_doc["notes"] = notes
            branch_map[branch_id] = branch_doc
            if search_keywords or blacklist_keywords:
                legacy_keywords[branch_id] = {
                    "core": search_keywords,
                    "blacklist": blacklist_keywords,
                }
            if reply_texts:
                legacy_quotes[branch_id] = reply_texts

        resolved_default = normalize_branch_id(
            default_branch,
            default=(next(iter(branch_map.keys()), DEFAULT_BRANCH_ID)),
        )
        if resolved_default not in branch_map:
            branch_map.setdefault(
                resolved_default,
                {"label": branch_label(resolved_default)},
            )

        document["default_branch"] = resolved_default
        document["branches"] = branch_map
        if legacy_keywords:
            document["nurture_keywords"] = legacy_keywords
        elif "nurture_keywords" in document:
            document.pop("nurture_keywords", None)
        if legacy_quotes:
            document["quote_texts"] = legacy_quotes
        elif "quote_texts" in document:
            document.pop("quote_texts", None)
        AppConfigManager.write_app_config(normalized_app_id, document)
        return self.get_profiles(normalized_app_id)

    def merge_branch_learning(
        self,
        app_id: str,
        *,
        branch_id: str,
        search_keywords: list[str] | None = None,
        reply_texts: list[str] | None = None,
        resource_namespace: str | None = None,
        payload_defaults: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.get_profiles(app_id)
        profiles = {item["branch_id"]: dict(item) for item in snapshot["branches"]}
        resolved_branch = normalize_branch_id(branch_id)
        profile = profiles.get(
            resolved_branch,
            {
                "branch_id": resolved_branch,
                "label": branch_label(resolved_branch),
                "search_keywords": [],
                "blacklist_keywords": [],
                "reply_texts": [],
                "resource_namespace": "",
                "reply_ai_type": "",
                "payload_defaults": {},
                "notes": "",
            },
        )
        if search_keywords:
            profile["search_keywords"] = _merge_texts(
                profile.get("search_keywords"),
                search_keywords,
            )
        if reply_texts:
            profile["reply_texts"] = _merge_texts(profile.get("reply_texts"), reply_texts)
        if resource_namespace not in (None, ""):
            profile["resource_namespace"] = str(resource_namespace).strip()
        if isinstance(payload_defaults, dict) and payload_defaults:
            merged_defaults = dict(profile.get("payload_defaults") or {})
            merged_defaults.update(_non_empty_payload_defaults(payload_defaults))
            profile["payload_defaults"] = merged_defaults
        profiles[resolved_branch] = profile
        ordered = sorted(
            profiles.values(),
            key=lambda item: (0 if item["branch_id"] == snapshot["default_branch"] else 1, item["branch_id"]),
        )
        return self.save_profiles(
            app_id,
            default_branch=snapshot["default_branch"],
            branches=ordered,
        )
