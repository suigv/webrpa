from __future__ import annotations

import json
import re


def _build_account_obj(account: str, password: str, twofa: str = "") -> dict[str, object]:
    return {
        "account": account,
        "password": password,
        "twofa": twofa,
        "email": "",
        "email_password": "",
        "token": "",
        "email_token": "",
        "status": "ready",
        "last_used": None,
        "error_msg": None,
    }


def _split_account_line(line: str) -> list[str]:
    text = str(line).strip()
    if not text:
        return []
    if "\t" in text:
        parts = [part.strip() for part in text.split("\t")]
    elif "," in text:
        parts = [part.strip() for part in text.split(",")]
    else:
        parts = [part.strip() for part in re.split(r"\s+", text)]
    while parts and parts[-1] == "":
        parts.pop()
    return parts


def _is_header_line(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    tokens = {p.strip().lower() for p in parts[:3] if p.strip()}
    account_aliases = {"account", "账号", "username", "user"}
    password_aliases = {"password", "密码", "passwd", "pwd"}
    return bool(tokens & account_aliases) and bool(tokens & password_aliases)


def parse_accounts_text(raw_text: str) -> dict[str, object]:
    lines = [line.strip() for line in str(raw_text).splitlines() if line.strip()]
    accounts: list[dict[str, object]] = []
    normalized_lines: list[str] = []
    errors: list[dict[str, object]] = []
    invalid = 0

    first_data_seen = False
    for idx, line in enumerate(lines, start=1):
        parts = _split_account_line(line)
        if not parts:
            continue
        if not first_data_seen and _is_header_line(parts):
            first_data_seen = True
            continue
        first_data_seen = True

        if len(parts) < 2:
            invalid += 1
            errors.append({"line": idx, "content": line, "error": "字段不足"})
            continue

        account = parts[0].strip()
        password = parts[1].strip()
        twofa = parts[2].strip() if len(parts) > 2 else ""
        if not account or not password:
            invalid += 1
            errors.append({"line": idx, "content": line, "error": "账号或密码为空"})
            continue

        obj = _build_account_obj(account=account, password=password, twofa=twofa)
        accounts.append(obj)
        normalized_lines.append(json.dumps(obj, ensure_ascii=False))

    return {
        "accounts": accounts,
        "normalized_lines": normalized_lines,
        "errors": errors,
        "valid": len(accounts),
        "invalid": invalid,
    }


def detect_delimiter(text: str) -> str:
    """智能侦测分隔符：优先匹配 ----, 然后是 |, \t, 最后是逗号或空格"""
    if not text:
        return ","

    # 取前 5 行进行采样
    lines = [line.strip() for line in text.splitlines() if line.strip()][:5]
    if not lines:
        return ","

    candidates = ["----", "|", "\t", ","]
    counts = dict.fromkeys(candidates, 0)

    for line in lines:
        for c in candidates:
            if c in line:
                counts[c] += line.count(c)

    # 找到出现频率最高且稳定的分隔符
    best_delimiter = max(counts, key=lambda key: counts[key])
    if counts[best_delimiter] > 0:
        return best_delimiter

    # 兜底：尝试匹配连续空格
    if re.search(r"\s{2,}", lines[0]):
        return "  "
    return ","


def parse_accounts_advanced(
    raw_text: str,
    delimiter: str | None = None,
    mapping: dict[int, str] | None = None,
) -> dict[str, object]:
    """
    高级解析逻辑：支持多字段映射并归一化为 JSON 字符串存储
    mapping 示例: { 0: "account", 1: "password", 5: "twofa" }
    """
    if not delimiter:
        delimiter = detect_delimiter(raw_text)

    # 默认映射
    if not mapping:
        mapping = {0: "account", 1: "password", 2: "twofa"}

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    accounts = []
    normalized_json_lines = []
    errors = []

    for idx, line in enumerate(lines, start=1):
        if delimiter == "  ":
            parts = [p.strip() for p in re.split(r"\s+", line) if p.strip()]
        else:
            parts = [p.strip() for p in line.split(delimiter)]

        if idx == 1:
            print(f"DEBUG: Delimiter='{delimiter}', Mapping={mapping}, First line parts={parts}")

        if len(parts) < 2:
            errors.append({"line": idx, "content": line, "error": "字段不足"})
            continue

        entry = {}
        for col_idx, field_name in mapping.items():
            col_idx = int(col_idx)
            if col_idx < len(parts):
                entry[field_name] = parts[col_idx]

        acc = entry.get("account")
        pwd = entry.get("password")

        if not acc or not pwd:
            errors.append({"line": idx, "content": line, "error": "账号或密码为空"})
            continue

        account_obj = _build_account_obj(account=acc, password=pwd, twofa=entry.get("twofa", ""))

        # Merge other fields from entry into account_obj (token, email, etc.)
        for field, value in entry.items():
            if field not in ["account", "password", "twofa"]:
                account_obj[field] = value

        accounts.append(account_obj)
        normalized_json_lines.append(json.dumps(account_obj, ensure_ascii=False))

    return {
        "delimiter": delimiter,
        "accounts": accounts,
        "normalized_lines": normalized_json_lines,
        "errors": errors,
        "valid": len(accounts),
    }


def parse_accounts_lines(lines: list[str]) -> list[dict[str, str]]:
    """将存储的 JSON 行列表解析回对象列表"""
    parsed: list[dict[str, str]] = []
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        try:
            parsed.append(json.loads(text))
        except Exception:
            # 彻底移除旧格式宽容处理，如果不是 JSON 则跳过
            continue
    return parsed
