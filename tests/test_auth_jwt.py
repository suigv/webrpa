# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

import json
import time

import jwt
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.server import app


def _make_token(secret: str) -> str:
    return jwt.encode(
        {
            "sub": "test-user",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        },
        secret,
        algorithm="HS256",
    )


def test_api_requires_bearer_when_auth_enabled(monkeypatch):
    secret = "test-secret-" + ("x" * 40)
    monkeypatch.setenv("MYT_AUTH_MODE", "jwt")
    monkeypatch.setenv("MYT_JWT_SECRET", secret)
    client = TestClient(app)

    r = client.get("/api/tasks/")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_api_accepts_valid_bearer_token(monkeypatch):
    secret = "test-secret-" + ("x" * 40)
    monkeypatch.setenv("MYT_AUTH_MODE", "jwt")
    monkeypatch.setenv("MYT_JWT_SECRET", secret)
    token = _make_token(secret)
    client = TestClient(app)

    r = client.get("/api/tasks/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_ws_rejects_without_token_when_auth_enabled(monkeypatch):
    secret = "test-secret-" + ("x" * 40)
    monkeypatch.setenv("MYT_AUTH_MODE", "jwt")
    monkeypatch.setenv("MYT_JWT_SECRET", secret)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/logs"):
        pass


def test_ws_accepts_bearer_token_via_subprotocol(monkeypatch):
    secret = "test-secret-" + ("x" * 40)
    monkeypatch.setenv("MYT_AUTH_MODE", "jwt")
    monkeypatch.setenv("MYT_JWT_SECRET", secret)
    token = _make_token(secret)
    client = TestClient(app)

    with client.websocket_connect("/ws/logs", subprotocols=[f"bearer.{token}"]) as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        reply = json.loads(ws.receive_text())
        assert reply["type"] == "pong"
