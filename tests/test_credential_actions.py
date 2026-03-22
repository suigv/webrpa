from __future__ import annotations

from types import SimpleNamespace

from _pytest.monkeypatch import MonkeyPatch

from engine.actions.credential_actions import credentials_checkout
from engine.models.runtime import ExecutionContext


def test_credentials_checkout_forwards_app_id_when_present(monkeypatch: MonkeyPatch):
    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict[str, object] | None = None, timeout: int = 0):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return SimpleNamespace(
            json=lambda: {
                "status": "ok",
                "account": {
                    "account": "scoped_user",
                    "password": "secret",
                    "twofa": "OTP-SECRET",
                },
            }
        )

    monkeypatch.setattr("engine.actions.credential_actions.requests.post", fake_post)

    context = ExecutionContext(payload={"app_id": "wechat"})
    result = credentials_checkout({}, context)

    assert result.ok is True
    assert captured["json"] == {"app_id": "wechat"}
    assert context.vars["creds"]["account"] == "scoped_user"
    assert context.vars["creds"]["twofa_secret"] == "OTP-SECRET"


def test_credentials_checkout_can_infer_app_id_from_package(monkeypatch: MonkeyPatch):
    captured: dict[str, object] = {}

    def fake_post(_url: str, json: dict[str, object] | None = None, timeout: int = 0):
        captured["json"] = json
        captured["timeout"] = timeout
        return SimpleNamespace(
            json=lambda: {
                "status": "ok",
                "account": {"account": "pkg_user", "password": "secret"},
            }
        )

    monkeypatch.setattr("engine.actions.credential_actions.requests.post", fake_post)
    def fake_find_app_by_package(package_name: str) -> str:
        return "telegram" if package_name == "org.telegram.messenger" else ""

    monkeypatch.setattr(
        "engine.actions.credential_actions.AppConfigManager.find_app_by_package",
        fake_find_app_by_package,
    )

    context = ExecutionContext(payload={"package": "org.telegram.messenger"})
    result = credentials_checkout({}, context)

    assert result.ok is True
    assert captured["json"] == {"app_id": "telegram"}
