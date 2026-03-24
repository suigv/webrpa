from __future__ import annotations

import json
import threading
from typing import Any

from core.account_parser import parse_accounts_advanced, parse_accounts_text
from core.account_store import AccountStore
from core.app_config import AppConfigManager
from core.business_profile import coerce_role_tags, normalize_branch_id
from core.data_store import read_lines

_accounts_lock = threading.Lock()
_account_store: AccountStore | None = None


def _get_store() -> AccountStore:
    global _account_store
    if _account_store is not None:
        return _account_store

    with _accounts_lock:
        if _account_store is None:
            store = AccountStore()
            # 自动迁移检查
            import os

            from core.paths import data_dir

            json_path = data_dir() / "accounts.json"
            if json_path.exists() and store.count_accounts() == 0:
                try:
                    # 使用已有的 core.data_store.read_lines 加载 JSON 行
                    lines = read_lines("accounts")
                    for line in lines:
                        try:
                            data = json.loads(line)
                            if isinstance(data, dict) and "account" in data:
                                store.upsert_account(data)
                        except Exception:
                            continue
                    # 迁移完成后重命名旧文件
                    target_bak = json_path.with_suffix(".json.migrated")
                    if not target_bak.exists():
                        os.rename(json_path, target_bak)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).error(f"Failed to migrate accounts from JSON: {e}")
            _account_store = store
        return _account_store


def get_accounts_raw_text() -> str:
    """返回所有账号的规整化展示 (模拟旧逻辑)"""
    accounts = _get_store().list_accounts()
    return "\n".join([json.dumps(a, ensure_ascii=False) for a in accounts])


def import_accounts_content(
    content: str,
    overwrite: bool,
    delimiter: str | None,
    mapping: dict[int, str] | None,
    app_id: str | None = "default",
    app_display_name: str | None = None,
    package_name: str | None = None,
    default_branch: str | None = None,
    role_tags: list[str] | None = None,
) -> dict[str, Any]:
    app_identity = AppConfigManager.ensure_app_config(
        app_id=app_id,
        display_name=app_display_name,
        package_name=package_name,
    )
    normalized_app_id = str(app_identity["app_id"]).strip().lower()
    if not normalized_app_id:
        raise ValueError("app_id is required")

    clean_mapping: dict[int, str] = {}
    if mapping:
        for key, value in mapping.items():
            try:
                clean_mapping[int(key)] = value
            except (ValueError, TypeError):
                continue

    if delimiter is None and not clean_mapping:
        parsed: dict[str, Any] = parse_accounts_text(content)
    else:
        parsed = parse_accounts_advanced(
            content, delimiter=delimiter or "", mapping=clean_mapping or None
        )

    accounts = parsed.get("accounts", [])
    if not isinstance(accounts, list):
        accounts = []

    errors = parsed.get("errors", [])
    valid = len(accounts)

    invalid_raw = parsed.get("invalid", 0)
    invalid = int(invalid_raw) if isinstance(invalid_raw, (int, float, str)) else 0

    store = _get_store()
    if overwrite:
        store.clear_all()

    for acc_data in accounts:
        if isinstance(acc_data, dict) and "account" in acc_data:
            acc_data["app_id"] = normalized_app_id
            acc_data["default_branch"] = normalize_branch_id(default_branch)
            acc_data["role_tags"] = coerce_role_tags(role_tags or [])
            store.upsert_account(acc_data)

    total_stored = store.count_accounts()

    return {
        "status": "ok",
        "stored": total_stored,
        "imported": len(accounts),
        "valid": valid,
        "invalid": invalid,
        "errors": errors if isinstance(errors, list) else [],
        "resolved_app": {
            "app_id": normalized_app_id,
            "display_name": app_identity.get("display_name"),
            "package_name": app_identity.get("package_name") or None,
            "created": bool(app_identity.get("created")),
        },
        "resolved_account_defaults": {
            "default_branch": normalize_branch_id(default_branch),
            "role_tags": coerce_role_tags(role_tags or []),
        },
    }


def update_account_fields(old_account: str, new_data: dict[str, Any]) -> bool:
    return _get_store().update_fields(old_account, new_data)


def update_account_status(account: str, status: str, error_msg: str | None = None) -> bool:
    return _get_store().update_status(account, status, error_msg)


def pop_account(
    app_id: str | None = None,
    *,
    branch_id: str | None = None,
    role_tags: list[str] | None = None,
) -> dict[str, Any] | None:
    normalized_app_id = None
    if app_id is not None:
        normalized_app_id = AppConfigManager.resolve_app_identity(app_id=app_id)["app_id"]
    return _get_store().pop_ready_account(
        app_id=normalized_app_id,
        branch_id=branch_id,
        role_tags=role_tags,
    )


def list_accounts(
    app_id: str | None = None,
    *,
    branch_id: str | None = None,
    role_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_app_id = None
    if app_id is not None:
        normalized_app_id = AppConfigManager.resolve_app_identity(app_id=app_id)["app_id"]
    return _get_store().list_accounts(
        app_id=normalized_app_id,
        branch_id=branch_id,
        role_tags=role_tags,
    )


def reset_accounts() -> int:
    return _get_store().reset_all_status(
        from_statuses=["in_progress", "bad_auth", "banned", "2fa_issue"], to_status="ready"
    )
