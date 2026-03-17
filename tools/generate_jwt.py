from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from typing import Any


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    cleaned = str(raw or "").strip().lower()
    if not cleaned:
        return default
    return cleaned in {"1", "true", "yes", "on"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Generate a JWT for WebRPA (HS256 by default). "
            "Recommended to pass the secret via env: MYT_JWT_SECRET."
        )
    )
    p.add_argument("--secret", default="", help="HMAC secret (fallback if MYT_JWT_SECRET unset)")
    p.add_argument("--alg", default=os.environ.get("MYT_JWT_ALGORITHMS", "HS256"), help="JWT alg")
    p.add_argument("--sub", default="operator", help="Subject (sub)")
    p.add_argument("--iss", default=os.environ.get("MYT_JWT_ISSUER", ""), help="Issuer (iss)")
    p.add_argument("--aud", default=os.environ.get("MYT_JWT_AUDIENCE", ""), help="Audience (aud)")
    p.add_argument("--ttl-seconds", type=int, default=24 * 3600, help="TTL in seconds")
    p.add_argument(
        "--require-exp",
        action="store_true",
        default=_parse_bool(os.environ.get("MYT_JWT_REQUIRE_EXP", "0"), default=False),
        help="Force exp claim even if ttl-seconds <= 0",
    )
    p.add_argument(
        "--kid",
        default="",
        help="Optional key id (kid) header (useful for secret rotation bookkeeping)",
    )
    p.add_argument(
        "--random-secret",
        action="store_true",
        help="Print a random 32-byte secret to stdout and exit",
    )
    return p


def _load_secret(args: argparse.Namespace) -> str:
    secret = os.environ.get("MYT_JWT_SECRET", "").strip() or str(args.secret or "").strip()
    if not secret:
        raise SystemExit("Missing secret: set MYT_JWT_SECRET or pass --secret")
    if len(secret.encode("utf-8")) < 32:
        print(
            "WARNING: HMAC key is shorter than 32 bytes; consider using a longer secret.",
            file=sys.stderr,
        )
    return secret


def _generate_token(args: argparse.Namespace, secret: str) -> str:
    import jwt

    now = int(time.time())
    payload: dict[str, Any] = {"sub": args.sub, "iat": now}
    ttl = int(args.ttl_seconds)
    if ttl > 0 or args.require_exp:
        payload["exp"] = now + max(1, ttl) if ttl > 0 else now + 24 * 3600
    if args.iss:
        payload["iss"] = args.iss
    if args.aud:
        payload["aud"] = args.aud

    headers: dict[str, Any] = {}
    if args.kid:
        headers["kid"] = args.kid

    return jwt.encode(payload, secret, algorithm=str(args.alg).strip(), headers=headers)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.random_secret:
        sys.stdout.write(secrets.token_urlsafe(48))
        sys.stdout.write("\n")
        return

    secret = _load_secret(args)
    token = _generate_token(args, secret)
    sys.stdout.write(token)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

