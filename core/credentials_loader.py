from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import pyotp


@dataclass
class Credentials:
    account: str
    password: str
    twofa_secret: str | None = None
    email: str | None = None
    email_password: str | None = None
    token: str | None = None
    email_token: str | None = None

    @property
    def username_or_email(self) -> str:
        """Alias for backward compatibility with existing plugins"""
        return self.account

    @property
    def twofa_code(self) -> str:
        """Dynamically generate 6-digit TOTP code if secret is present"""
        if not self.twofa_secret:
            return ""
        try:
            clean_secret = str(self.twofa_secret).replace(" ", "").strip()
            totp = pyotp.TOTP(clean_secret)
            return totp.now()
        except Exception:
            return ""


def _allowed_credential_roots() -> list[Path]:
    from core.system_settings_loader import get_credential_allowlist
    raw = get_credential_allowlist()
    roots: list[Path] = []
    roots.append(Path(".").resolve())
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
    """加载凭据，支持 JSON 字符串或本地文件路径"""
    ref = str(credentials_ref or "").strip()
    if not ref:
        raise ValueError("credentials_ref is required")

    # 如果是直接传入的 JSON 字符串（批量下发时常用）
    if ref.startswith("{") and ref.endswith("}"):
        try:
            payload = json.loads(ref)
            return _build_creds(payload)
        except Exception as exc:
            raise ValueError(f"Direct credentials JSON is invalid: {exc}")

    raw_path = Path(ref).expanduser()
    if raw_path.is_symlink():
        raise ValueError("credentials_ref symlink is not allowed")

    path = raw_path.resolve()
    if not path.exists() or not path.is_file():
        raise ValueError(f"credentials_ref file does not exist: {path}")
    if not _is_allowed_path(path):
        raise ValueError(f"credentials_ref path is outside allowlist: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"credentials_ref JSON file is invalid: {exc}")

    return _build_creds(payload)


def _build_creds(payload: dict) -> Credentials:
    """从结构化字典构造 Credentials 对象"""
    if not isinstance(payload, dict):
        raise ValueError("credentials must be a JSON object")

    account = str(payload.get("account") or payload.get("username_or_email") or "").strip()
    password = str(payload.get("password") or "").strip()
    
    if not account or not password:
        raise ValueError("credentials requires at least account and password")

    return Credentials(
        account=account,
        password=password,
        twofa_secret=payload.get("twofa_secret") or payload.get("twofa") or payload.get("otp_secret"),
        email=payload.get("email"),
        email_password=payload.get("email_password"),
        token=payload.get("token"),
        email_token=payload.get("email_token")
    )
