from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, WebSocket


@dataclass(frozen=True)
class JwtSettings:
    enabled: bool
    secret: str
    algorithms: tuple[str, ...]
    issuer: str | None
    audience: str | None
    leeway_seconds: int
    require_exp: bool


def _parse_bool(raw: str, default: bool = False) -> bool:
    cleaned = (raw or "").strip().lower()
    if not cleaned:
        return default
    return cleaned in {"1", "true", "yes", "on"}


def get_jwt_settings() -> JwtSettings:
    mode = os.environ.get("MYT_AUTH_MODE", "disabled").strip().lower()
    enabled = mode in {"jwt", "enabled", "on", "true", "1"}

    secret = os.environ.get("MYT_JWT_SECRET", "").strip()
    alg_raw = os.environ.get("MYT_JWT_ALGORITHMS", "HS256")
    algorithms = tuple(item.strip() for item in alg_raw.split(",") if item.strip())
    issuer = os.environ.get("MYT_JWT_ISSUER", "").strip() or None
    audience = os.environ.get("MYT_JWT_AUDIENCE", "").strip() or None
    leeway_seconds = int(os.environ.get("MYT_JWT_LEEWAY_SECONDS", "0").strip() or "0")
    require_exp = _parse_bool(os.environ.get("MYT_JWT_REQUIRE_EXP", "0"), default=False)

    if enabled and not secret:
        raise RuntimeError("MYT_AUTH_MODE enabled but MYT_JWT_SECRET is not set")
    if enabled and not algorithms:
        raise RuntimeError("MYT_AUTH_MODE enabled but MYT_JWT_ALGORITHMS is empty")

    return JwtSettings(
        enabled=enabled,
        secret=secret,
        algorithms=algorithms,
        issuer=issuer,
        audience=audience,
        leeway_seconds=max(0, int(leeway_seconds)),
        require_exp=require_exp,
    )


def _extract_bearer_from_authorization(authorization: str | None) -> str | None:
    raw = str(authorization or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        token = raw[7:].strip()
        return token or None
    return None


def _decode_jwt(token: str, settings: JwtSettings) -> dict[str, Any]:
    import jwt

    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": settings.audience is not None,
        "verify_iss": settings.issuer is not None,
        "require": ["exp"] if settings.require_exp else [],
    }
    payload = jwt.decode(
        token,
        settings.secret,
        algorithms=list(settings.algorithms),
        audience=settings.audience,
        issuer=settings.issuer,
        options=options,
        leeway=settings.leeway_seconds,
    )
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="invalid token payload type")
    return payload


def require_http_jwt(request: Request, settings: JwtSettings | None = None) -> dict[str, Any]:
    settings = settings or get_jwt_settings()
    if not settings.enabled:
        return {}

    token = _extract_bearer_from_authorization(request.headers.get("authorization"))
    if not token:
        raise HTTPException(
            status_code=401,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return _decode_jwt(token, settings)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"invalid bearer token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _extract_ws_bearer_from_subprotocol(websocket: WebSocket) -> tuple[str | None, str | None]:
    """
    Browsers cannot reliably set Authorization headers for WebSocket handshakes.
    We support passing the JWT via `Sec-WebSocket-Protocol` as: `bearer.<jwt>`.

    Returns (token, accepted_subprotocol).
    """
    proto_raw = websocket.headers.get("sec-websocket-protocol")
    if not proto_raw:
        return None, None

    # Header is a comma-separated list.
    parts = [p.strip() for p in proto_raw.split(",") if p.strip()]
    for p in parts:
        lower = p.lower()
        if lower.startswith("bearer."):
            token = p[len("bearer.") :].strip()
            if token:
                return token, p
    return None, None


def require_ws_jwt(
    websocket: WebSocket, settings: JwtSettings | None = None
) -> tuple[dict[str, Any], str | None]:
    settings = settings or get_jwt_settings()
    if not settings.enabled:
        return {}, None

    token = _extract_bearer_from_authorization(websocket.headers.get("authorization"))
    accepted_subprotocol: str | None = None
    if not token:
        token, accepted_subprotocol = _extract_ws_bearer_from_subprotocol(websocket)
    if not token:
        raise HTTPException(status_code=4401, detail="missing bearer token")

    try:
        payload = _decode_jwt(token, settings)
    except Exception as exc:
        raise HTTPException(status_code=4401, detail=f"invalid bearer token: {exc}") from exc

    # Soft sanity check for clock skew; helps debugging.
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and float(exp) < time.time() - settings.leeway_seconds:
        raise HTTPException(status_code=4401, detail="token expired")
    return payload, accepted_subprotocol
