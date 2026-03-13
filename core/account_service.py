from __future__ import annotations

import json
from datetime import datetime
import threading
from typing import Any

from core.account_parser import parse_accounts_advanced, parse_accounts_lines, parse_accounts_text
from core.data_store import read_lines, read_text, write_lines

_accounts_lock = threading.Lock()


def get_accounts_raw_text() -> str:
    return read_text("accounts")


def import_accounts_content(
    content: str,
    overwrite: bool,
    delimiter: str | None,
    mapping: dict[int, str] | None,
) -> dict[str, Any]:
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
        parsed = parse_accounts_advanced(content, delimiter=delimiter or "", mapping=clean_mapping or None)

    normalized_lines_obj = parsed.get("normalized_lines", [])
    if isinstance(normalized_lines_obj, list):
        new_lines: list[str] = [line for line in normalized_lines_obj if isinstance(line, str)]
    else:
        new_lines = []

    errors = parsed.get("errors", [])
    valid_raw = parsed.get("valid", len(new_lines))
    if isinstance(valid_raw, (int, float, str)):
        valid = int(valid_raw)
    else:
        valid = len(new_lines)

    invalid_raw = parsed.get("invalid", 0)
    if isinstance(invalid_raw, (int, float, str)):
        invalid = int(invalid_raw)
    else:
        invalid = 0

    if overwrite:
        merged_lines: list[str] = new_lines
    else:
        existing_lines = [line for line in read_lines("accounts") if isinstance(line, str)]
        merged_lines = existing_lines + new_lines

    write_lines("accounts", merged_lines)
    return {
        "status": "ok",
        "stored": len(merged_lines),
        "imported": len(new_lines),
        "valid": valid,
        "invalid": invalid,
        "errors": errors if isinstance(errors, list) else [],
    }


def update_account_fields(old_account: str, new_data: dict[str, Any]) -> bool:
    lines = read_lines("accounts")
    updated_lines: list[str] = []
    found = False

    for line in lines:
        try:
            item = json.loads(line)
            if item.get("account") == old_account:
                for key, value in new_data.items():
                    item[key] = value
                updated_lines.append(json.dumps(item, ensure_ascii=False))
                found = True
            else:
                updated_lines.append(line)
        except Exception:
            updated_lines.append(line)

    if found:
        write_lines("accounts", updated_lines)
    return found


def update_account_status(account: str, status: str, error_msg: str | None = None) -> bool:
    lines = read_lines("accounts")
    updated_lines: list[str] = []
    found = False

    for line in lines:
        try:
            item = json.loads(line)
            if item.get("account") == account:
                item["status"] = status
                if error_msg:
                    item["error_msg"] = error_msg
                updated_lines.append(json.dumps(item, ensure_ascii=False))
                found = True
            else:
                updated_lines.append(line)
        except Exception:
            updated_lines.append(line)

    if found:
        write_lines("accounts", updated_lines)
    return found


def pop_account() -> dict[str, Any] | None:
    with _accounts_lock:
        lines = read_lines("accounts")
        updated_lines: list[str] = []
        target_account: dict[str, Any] | None = None

        for line in lines:
            try:
                item = json.loads(line)
                if target_account is None and item.get("status") == "ready":
                    item["status"] = "in_progress"
                    item["last_used"] = str(datetime.now())
                    target_account = item
                    updated_lines.append(json.dumps(item, ensure_ascii=False))
                else:
                    updated_lines.append(line)
            except Exception:
                updated_lines.append(line)

        if target_account:
            write_lines("accounts", updated_lines)
            return target_account
    return None


def list_accounts() -> list[dict[str, Any]]:
    return parse_accounts_lines(read_lines("accounts"))


def reset_accounts() -> int:
    lines = read_lines("accounts")
    updated_lines: list[str] = []
    count = 0

    for line in lines:
        try:
            item = json.loads(line)
            if item.get("status") in ["in_progress", "bad_auth", "banned", "2fa_issue"]:
                item["status"] = "ready"
                item["error_msg"] = None
                updated_lines.append(json.dumps(item, ensure_ascii=False))
                count += 1
            else:
                updated_lines.append(line)
        except Exception:
            updated_lines.append(line)

    write_lines("accounts", updated_lines)
    return count
