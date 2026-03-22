from __future__ import annotations

import logging
import os
from typing import Any

import requests

from core.app_config import AppConfigManager
from core.credentials_loader import load_credentials_from_ref
from engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)


def _serialize_credentials(creds: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "account": str(getattr(creds, "account", "") or ""),
        "username_or_email": str(getattr(creds, "username_or_email", "") or ""),
        "password": str(getattr(creds, "password", "") or ""),
        "twofa_secret": getattr(creds, "twofa_secret", None),
        "twofa_code": str(getattr(creds, "twofa_code", "") or ""),
        "email": getattr(creds, "email", None),
        "email_password": getattr(creds, "email_password", None),
        "token": getattr(creds, "token", None),
        "email_token": getattr(creds, "email_token", None),
    }
    return payload


def credentials_load(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    """从引用或 JSON 字符串加载凭据。"""
    credentials_ref = str(
        params.get("credentials_ref") or context.get_session_default("credentials_ref") or ""
    )
    save_as = str(params.get("save_as", "creds"))

    if not credentials_ref:
        return ActionResult(ok=False, code="missing_ref", message="credentials_ref param required")

    try:
        creds = load_credentials_from_ref(credentials_ref)
        context.vars[save_as] = _serialize_credentials(creds)
        context.vars[f"{save_as}_obj"] = creds
        return ActionResult(ok=True, code="ok", message=f"credentials loaded as {save_as}")
    except Exception as exc:
        return ActionResult(ok=False, code="credential_error", message=str(exc))


def credentials_checkout(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    """从账号池中‘弹出’（POP）下一个可用账号。实现‘池子-1’逻辑。"""
    save_as = str(params.get("save_as", "creds"))

    # 获取本地 API 基地址，默认 8001 (匹配 AGENTS.md 验证命令)
    port = os.environ.get("MYT_API_PORT", "8001")
    host = os.environ.get("MYT_API_HOST", "127.0.0.1")
    url = f"http://{host}:{port}/api/data/accounts/pop"
    request_payload = _build_checkout_request_payload(params, context)

    try:
        if request_payload is None:
            resp = requests.post(url, timeout=10)
        else:
            resp = requests.post(url, json=request_payload, timeout=10)
        data = resp.json()

        if data.get("status") == "ok":
            from core.credentials_loader import _build_creds

            account_data = data.get("account")
            creds = _build_creds(account_data)
            context.vars[save_as] = _serialize_credentials(creds)
            context.vars[f"{save_as}_obj"] = creds
            return ActionResult(
                ok=True, code="ok", message=f"Account '{creds.account}' checked out from pool"
            )
        else:
            return ActionResult(
                ok=False, code="pool_empty", message=data.get("message", "No accounts available")
            )

    except Exception as exc:
        return ActionResult(
            ok=False, code="request_failed", message=f"Failed to checkout account: {exc}"
        )


def _build_checkout_request_payload(
    params: dict[str, Any], context: ExecutionContext
) -> dict[str, Any] | None:
    app_id = _resolve_checkout_app_id(params, context)
    if not app_id:
        return None
    return {"app_id": app_id}


def _resolve_checkout_app_id(params: dict[str, Any], context: ExecutionContext) -> str:
    payload = context.payload if isinstance(context.payload, dict) else {}
    for source in (params, payload):
        for key in ("app_id", "app"):
            raw = str(source.get(key) or "").strip().lower()
            if raw:
                return raw

    for source in (params, payload):
        package = str(source.get("package") or "").strip()
        if not package:
            continue
        mapped = AppConfigManager.find_app_by_package(package)
        if mapped:
            return mapped
    return ""
