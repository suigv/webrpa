from __future__ import annotations

import json
from typing import Any, Callable

from core.data_store import read_lines, write_lines


class AccountFeedbackService:
    def __init__(
        self,
        *,
        read_account_lines: Callable[[str], list[str]] = read_lines,
        write_account_lines: Callable[[str, list[str]], None] = write_lines,
    ) -> None:
        self._read_account_lines = read_account_lines
        self._write_account_lines = write_account_lines

    def handle_terminal_failure(self, payload: dict[str, Any], error: str) -> None:
        account_name = self._account_name_from_payload(payload)
        if not account_name:
            return

        target_status = self._target_status_for_error(error)
        if not target_status:
            return

        try:
            lines = self._read_account_lines("accounts")
            updated: list[str] = []
            found = False
            for line in lines:
                try:
                    item = json.loads(line)
                except Exception:
                    updated.append(line)
                    continue
                if item.get("account") != account_name:
                    updated.append(line)
                    continue
                item["status"] = target_status
                item["error_msg"] = error
                updated.append(json.dumps(item))
                found = True
            if found:
                self._write_account_lines("accounts", updated)
        except Exception:
            return

    def _account_name_from_payload(self, payload: dict[str, Any]) -> str | None:
        ref = str(payload.get("credentials_ref") or "").strip()
        if not ref:
            return None
        if not (ref.startswith("{") and ref.endswith("}")):
            return None
        try:
            creds = json.loads(ref)
        except Exception:
            return None
        if not isinstance(creds, dict):
            return None
        account_name = creds.get("account") or creds.get("username_or_email")
        if not account_name:
            return None
        return str(account_name)

    def _target_status_for_error(self, error: str) -> str | None:
        error_lower = error.lower()
        if any(token in error_lower for token in ["wrong password", "incorrect", "bad credentials"]):
            return "bad_auth"
        if any(token in error_lower for token in ["suspended", "banned", "locked"]):
            return "banned"
        if "2fa" in error_lower:
            return "2fa_issue"
        return None
