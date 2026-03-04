from __future__ import annotations

import re


def _is_header_line(line: str) -> bool:
    lowered = line.lower()
    has_account = ("账号" in line) or ("账户" in line) or ("account" in lowered) or ("username" in lowered)
    has_password = ("密码" in line) or ("password" in lowered) or ("pass" in lowered)
    return has_account and has_password


def _split_row(line: str) -> list[str]:
    if "," in line:
        return [part.strip() for part in line.split(",")]
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    return [part.strip() for part in re.split(r"\s+", line)]


def parse_accounts_text(raw_text: str) -> dict[str, object]:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    normalized_lines: list[str] = []
    accounts: list[dict[str, str]] = []
    errors: list[dict[str, object]] = []

    for idx, line in enumerate(lines, start=1):
        if _is_header_line(line):
            continue
        parts = _split_row(line)
        if len(parts) < 2:
            errors.append({"line": idx, "content": line, "error": "requires at least account and password"})
            continue

        account = str(parts[0]).strip()
        password = str(parts[1]).strip()
        twofa = str(parts[2]).strip() if len(parts) >= 3 else ""

        if not account or not password:
            errors.append({"line": idx, "content": line, "error": "account or password is empty"})
            continue

        accounts.append({"account": account, "password": password, "twofa": twofa})
        normalized_lines.append(f"{account},{password},{twofa}")

    return {
        "accounts": accounts,
        "normalized_lines": normalized_lines,
        "errors": errors,
        "total": len(lines),
        "valid": len(accounts),
        "invalid": len(errors),
    }


def parse_accounts_lines(lines: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        if _is_header_line(text):
            continue
        parts = _split_row(text)
        if len(parts) < 2:
            continue
        account = str(parts[0]).strip()
        password = str(parts[1]).strip()
        twofa = str(parts[2]).strip() if len(parts) >= 3 else ""
        if account and password:
            parsed.append({"account": account, "password": password, "twofa": twofa})
    return parsed
