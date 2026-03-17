import os

from fastapi.testclient import TestClient


def _make_token(secret: str) -> str:
    import jwt

    payload = {"sub": "tester", "iat": 1, "exp": 10_000_000_000}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_openapi_json_unprotected_by_default() -> None:
    old = {
        "MYT_AUTH_MODE": os.environ.pop("MYT_AUTH_MODE", None),
        "MYT_JWT_SECRET": os.environ.pop("MYT_JWT_SECRET", None),
        "MYT_AUTH_PROTECT_OPENAPI": os.environ.pop("MYT_AUTH_PROTECT_OPENAPI", None),
    }

    try:
        from api.server import app

        client = TestClient(app)
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert r.json().get("openapi")
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_openapi_json_requires_bearer_when_enabled() -> None:
    old = {
        "MYT_AUTH_MODE": os.environ.get("MYT_AUTH_MODE"),
        "MYT_JWT_SECRET": os.environ.get("MYT_JWT_SECRET"),
        "MYT_AUTH_PROTECT_OPENAPI": os.environ.get("MYT_AUTH_PROTECT_OPENAPI"),
    }

    os.environ["MYT_AUTH_MODE"] = "jwt"
    os.environ["MYT_JWT_SECRET"] = "a" * 40
    os.environ["MYT_AUTH_PROTECT_OPENAPI"] = "1"

    try:
        from api.server import app

        client = TestClient(app)

        r1 = client.get("/openapi.json")
        assert r1.status_code == 401

        token = _make_token("a" * 40)
        r2 = client.get("/openapi.json", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json().get("openapi")
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
