from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass
class Credentials:
    username_or_email: str
    password: str


def _allowed_credential_roots() -> list[Path]:
    raw = os.environ.get("MYT_CREDENTIAL_ALLOWLIST", "/etc/myt")
    roots: list[Path] = []
    for item in raw.split(":"):
        cleaned = item.strip()
        if not cleaned:
            continue
        roots.append(Path(cleaned).expanduser().resolve())
    return roots


def _is_allowed_path(path: Path) -> bool:
    for root in _allowed_credential_roots():
        if path == root or root in path.parents:
            return True
    return False


def load_credentials_from_ref(credentials_ref: str) -> Credentials:
    ref = str(credentials_ref or "").strip()
    if not ref:
        raise ValueError("credentials_ref is required")

    raw_path = Path(ref).expanduser()
    if raw_path.is_symlink():
        raise ValueError("credentials_ref symlink is not allowed")

    path = raw_path.resolve()
    if not path.exists() or not path.is_file():
        raise ValueError("credentials_ref file does not exist")
    if not _is_allowed_path(path):
        raise ValueError("credentials_ref path is outside allowlist")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("credentials_ref JSON is invalid") from exc

    if not isinstance(payload, dict):
        raise ValueError("credentials JSON must be object")

    username = str(payload.get("username_or_email") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not username or not password:
        raise ValueError("credentials JSON requires username_or_email and password")

    return Credentials(username_or_email=username, password=password)
